from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import (
    DemandRequest,
    Crop,
    Shop,
    UserRole,
)
from auth import get_current_user
from notification_service import create_notification, notify_role
from websocket import manager

router = APIRouter(
    prefix="/demand",
    tags=["Demand"]
)


# =========================
# SCHEMAS
# =========================

class DemandCreate(BaseModel):
    crop_id: UUID
    quantity_kg: float = Field(gt=0)
    required_by: date


class DemandUpdate(BaseModel):
    quantity_kg: float | None = Field(default=None, gt=0)
    required_by: date | None = None
    status: str | None = None


DEMAND_STATUSES = {"open", "approved", "rejected", "planned", "fulfilled"}


async def _get_demand_or_404(db: AsyncSession, demand_id: UUID) -> DemandRequest:
    demand = await db.scalar(select(DemandRequest).where(DemandRequest.id == demand_id))
    if not demand:
        raise HTTPException(status_code=404, detail="Demand not found")
    return demand


async def _notify_demand_status(
    db: AsyncSession,
    demand: DemandRequest,
    status_value: str,
    notification_type: str,
) -> None:
    crop = await db.scalar(select(Crop).where(Crop.id == demand.crop_id))
    shop = await db.scalar(select(Shop).where(Shop.id == demand.shop_id))
    if shop:
        await create_notification(
            db,
            shop.user_id,
            f"Your demand request for {crop.crop_name if crop else 'a crop'} is now {status_value}.",
            notification_type,
        )


async def _admin_set_demand_status(
    demand_id: UUID,
    status_value: str,
    event: str,
    db: AsyncSession,
    current_user,
):
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admins only")
    demand = await _get_demand_or_404(db, demand_id)
    demand.status = status_value
    await _notify_demand_status(db, demand, status_value, f"demand.{status_value}")
    await db.flush()
    await db.refresh(demand)
    await db.commit()
    await manager.broadcast("supply-demand", {"event": event, "demand": _demand_event_payload(demand)})
    return {"message": f"Demand {status_value}", "demand": demand}


def _demand_event_payload(demand: DemandRequest) -> dict:
    return {
        "id": str(demand.id),
        "crop_id": str(demand.crop_id),
        "quantity_kg": demand.quantity_kg,
        "required_by": demand.required_by.isoformat(),
        "status": demand.status,
    }


# =========================
# CREATE DEMAND
# =========================

@router.post("/")
async def create_demand(
    data: DemandCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role != UserRole.shop:
        raise HTTPException(
            status_code=403,
            detail="Only shops can create demand requests"
        )

    crop_result = await db.execute(
        select(Crop).where(Crop.id == data.crop_id)
    )
    crop = crop_result.scalar_one_or_none()

    if not crop:
        raise HTTPException(
            status_code=404,
            detail="Crop not found"
        )

    shop_result = await db.execute(
        select(Shop).where(Shop.user_id == current_user.id)
    )
    shop = shop_result.scalar_one_or_none()

    if not shop:
        raise HTTPException(
            status_code=404,
            detail="Shop profile not found"
        )

    demand = DemandRequest(
        shop_id=shop.id,
        crop_id=data.crop_id,
        quantity_kg=data.quantity_kg,
        required_by=data.required_by,
        status="open"
    )

    db.add(demand)
    await db.flush()
    await db.refresh(demand)
    await notify_role(
        db,
        UserRole.admin,
        f"{current_user.name} requested {demand.quantity_kg} kg of {crop.crop_name}.",
        "demand.created",
    )
    await create_notification(
        db,
        current_user.id,
        f"Your demand request for {crop.crop_name} was created.",
        "demand.created",
    )
    await db.commit()

    await manager.broadcast("supply-demand", {"event": "demand.created", "demand": _demand_event_payload(demand)})

    return {
        "message": "Demand request created",
        "demand": demand
    }


# =========================
# GET ALL DEMANDS
# ADMIN ONLY
# =========================

@router.get("/")
async def get_all_demands(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=403,
            detail="Admins only"
        )

    result = await db.execute(
        select(DemandRequest)
    )

    return result.scalars().all()


# =========================
# GET MY DEMANDS
# SHOP ONLY
# =========================

@router.get("/me")
async def get_my_demands(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role != UserRole.shop:
        raise HTTPException(
            status_code=403,
            detail="Shops only"
        )

    shop_result = await db.execute(
        select(Shop).where(
            Shop.user_id == current_user.id
        )
    )

    shop = shop_result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop profile not found")

    result = await db.execute(
        select(DemandRequest).where(
            DemandRequest.shop_id == shop.id
        )
    )

    return result.scalars().all()


# =========================
# GET SINGLE DEMAND
# =========================

@router.get("/{demand_id}")
async def get_demand(
    demand_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    result = await db.execute(
        select(DemandRequest).where(
            DemandRequest.id == demand_id
        )
    )

    demand = result.scalar_one_or_none()

    if not demand:
        raise HTTPException(
            status_code=404,
            detail="Demand not found"
        )

    if current_user.role == UserRole.shop:
        shop_result = await db.execute(select(Shop).where(Shop.user_id == current_user.id))
        shop = shop_result.scalar_one_or_none()
        if not shop or demand.shop_id != shop.id:
            raise HTTPException(status_code=403, detail="Not allowed")
    elif current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Not allowed")

    return demand


# =========================
# UPDATE DEMAND
# =========================

@router.put("/{demand_id}")
async def update_demand(
    demand_id: UUID,
    data: DemandUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    result = await db.execute(
        select(DemandRequest).where(
            DemandRequest.id == demand_id
        )
    )

    demand = result.scalar_one_or_none()

    if not demand:
        raise HTTPException(
            status_code=404,
            detail="Demand not found"
        )

    if current_user.role == UserRole.shop:
        shop_result = await db.execute(select(Shop).where(Shop.user_id == current_user.id))
        shop = shop_result.scalar_one_or_none()
        if not shop or demand.shop_id != shop.id:
            raise HTTPException(status_code=403, detail="Not allowed")
    elif current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=403,
            detail="Not allowed"
        )

    if data.quantity_kg is not None:
        demand.quantity_kg = data.quantity_kg

    if data.required_by is not None:
        demand.required_by = data.required_by

    if data.status is not None:
        if data.status not in DEMAND_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid demand status")
        demand.status = data.status

    crop_result = await db.execute(select(Crop).where(Crop.id == demand.crop_id))
    crop = crop_result.scalar_one_or_none()
    shop_result = await db.execute(select(Shop).where(Shop.id == demand.shop_id))
    shop = shop_result.scalar_one_or_none()
    if shop:
        await create_notification(
            db,
            shop.user_id,
            f"Your demand request for {crop.crop_name if crop else 'a crop'} is now {demand.status}.",
            "demand.updated",
        )
    await db.flush()
    await db.refresh(demand)
    await db.commit()

    await manager.broadcast("supply-demand", {"event": "demand.updated", "demand": _demand_event_payload(demand)})

    return {
        "message": "Demand updated",
        "demand": demand
    }


@router.put("/{demand_id}/approve")
async def approve_demand(
    demand_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await _admin_set_demand_status(demand_id, "approved", "demand.approved", db, current_user)


@router.put("/{demand_id}/reject")
async def reject_demand(
    demand_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await _admin_set_demand_status(demand_id, "rejected", "demand.rejected", db, current_user)


@router.put("/{demand_id}/planned")
async def planned_demand(
    demand_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await _admin_set_demand_status(demand_id, "planned", "demand.planned", db, current_user)


@router.get("/insights/high-demand")
async def high_demand_crops(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.farmer}:
        raise HTTPException(status_code=403, detail="Admins or farmers only")

    rows = (
        await db.execute(
            select(Crop.crop_name, DemandRequest.status, func.sum(DemandRequest.quantity_kg))
            .join(Crop, DemandRequest.crop_id == Crop.id)
            .where(DemandRequest.status.in_(["open", "approved", "planned"]))
            .group_by(Crop.crop_name, DemandRequest.status)
            .order_by(func.sum(DemandRequest.quantity_kg).desc())
            .limit(10)
        )
    ).all()

    return [
        {"crop_name": crop_name, "status": status_value, "quantity_kg": float(quantity or 0)}
        for crop_name, status_value, quantity in rows
    ]


# =========================
# DELETE DEMAND
# =========================

@router.delete("/{demand_id}")
async def delete_demand(
    demand_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    result = await db.execute(
        select(DemandRequest).where(
            DemandRequest.id == demand_id
        )
    )

    demand = result.scalar_one_or_none()

    if not demand:
        raise HTTPException(
            status_code=404,
            detail="Demand not found"
        )

    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=403,
            detail="Admins only"
        )

    await db.delete(demand)
    await db.commit()

    return {
        "message": "Demand deleted"
    }
