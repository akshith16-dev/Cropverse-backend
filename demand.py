from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import (
    DemandRequest,
    Crop,
    Shop,
    UserRole,
)
from auth import get_current_user

router = APIRouter(
    prefix="/demand",
    tags=["Demand"]
)


# =========================
# SCHEMAS
# =========================

class DemandCreate(BaseModel):
    crop_id: UUID
    quantity_kg: float
    required_by: date


class DemandUpdate(BaseModel):
    quantity_kg: float | None = None
    required_by: date | None = None
    status: str | None = None


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
    await db.commit()

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

    if current_user.role not in [
        UserRole.admin,
        UserRole.shop
    ]:
        raise HTTPException(
            status_code=403,
            detail="Not allowed"
        )

    if data.quantity_kg is not None:
        demand.quantity_kg = data.quantity_kg

    if data.required_by is not None:
        demand.required_by = data.required_by

    if data.status is not None:
        demand.status = data.status

    await db.flush()
    await db.refresh(demand)
    await db.commit()

    return {
        "message": "Demand updated",
        "demand": demand
    }


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
