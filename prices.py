from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from auth import get_current_user

from models import (
    MarketPrice,
    Crop,
    UserRole
)
from notification_service import notify_all
from websocket import manager

router = APIRouter(
    prefix="/prices",
    tags=["Prices"]
)


# =========================
# SCHEMAS
# =========================

class PriceCreate(BaseModel):
    crop_id: UUID
    price_per_kg: float = Field(gt=0)
    fair_price: float = Field(gt=0)
    market_name: str = Field(min_length=2, max_length=100)


class PriceUpdate(BaseModel):
    price_per_kg: float | None = Field(default=None, gt=0)
    fair_price: float | None = Field(default=None, gt=0)
    market_name: str | None = Field(default=None, min_length=2, max_length=100)


# =========================
# ADD PRICE
# ADMIN ONLY
# =========================

@router.post("/")
async def create_price(
    data: PriceCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=403,
            detail="Admins only"
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

    price = MarketPrice(
        crop_id=data.crop_id,
        price_per_kg=data.price_per_kg,
        fair_price=data.fair_price,
        market_name=data.market_name
    )

    db.add(price)

    await db.flush()
    await db.refresh(price)
    await notify_all(
        db,
        f"{crop.crop_name} price was added for {price.market_name}: ₹{price.price_per_kg}/kg.",
        "price.created",
    )
    await db.commit()

    await manager.broadcast("prices", {"event": "price.created", "price": {"id": str(price.id), "crop_id": str(price.crop_id), "price_per_kg": price.price_per_kg, "fair_price": price.fair_price, "market_name": price.market_name, "recorded_at": price.recorded_at.isoformat()}})

    return {
        "message": "Price added successfully",
        "price": price
    }


# =========================
# GET ALL PRICES
# =========================

@router.get("/")
async def get_all_prices(
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(MarketPrice)
        .order_by(desc(MarketPrice.recorded_at))
    )

    return result.scalars().all()


# =========================
# GET CROP PRICE HISTORY
# =========================

@router.get("/crop/{crop_id}")
async def get_crop_prices(
    crop_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(MarketPrice)
        .where(MarketPrice.crop_id == crop_id)
        .order_by(desc(MarketPrice.recorded_at))
    )

    return result.scalars().all()


# =========================
# GET PRICE BY ID
# =========================

@router.get("/{price_id}")
async def get_price(
    price_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(MarketPrice)
        .where(MarketPrice.id == price_id)
    )

    price = result.scalar_one_or_none()

    if not price:
        raise HTTPException(
            status_code=404,
            detail="Price record not found"
        )

    return price


# =========================
# UPDATE PRICE
# ADMIN ONLY
# =========================

@router.put("/{price_id}")
async def update_price(
    price_id: UUID,
    data: PriceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=403,
            detail="Admins only"
        )

    result = await db.execute(
        select(MarketPrice)
        .where(MarketPrice.id == price_id)
    )

    price = result.scalar_one_or_none()

    if not price:
        raise HTTPException(
            status_code=404,
            detail="Price record not found"
        )

    if data.price_per_kg is not None:
        price.price_per_kg = data.price_per_kg

    if data.fair_price is not None:
        price.fair_price = data.fair_price

    if data.market_name is not None:
        price.market_name = data.market_name

    crop_result = await db.execute(select(Crop).where(Crop.id == price.crop_id))
    crop = crop_result.scalar_one_or_none()
    await db.flush()
    await db.refresh(price)
    await notify_all(
        db,
        f"{crop.crop_name if crop else 'Crop'} price was updated for {price.market_name}: ₹{price.price_per_kg}/kg.",
        "price.updated",
    )
    await db.commit()

    await manager.broadcast("prices", {"event": "price.updated", "price": {"id": str(price.id), "crop_id": str(price.crop_id), "price_per_kg": price.price_per_kg, "fair_price": price.fair_price, "market_name": price.market_name, "recorded_at": price.recorded_at.isoformat()}})

    return {
        "message": "Price updated",
        "price": price
    }


# =========================
# DELETE PRICE
# ADMIN ONLY
# =========================

@router.delete("/{price_id}")
async def delete_price(
    price_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=403,
            detail="Admins only"
        )

    result = await db.execute(
        select(MarketPrice)
        .where(MarketPrice.id == price_id)
    )

    price = result.scalar_one_or_none()

    if not price:
        raise HTTPException(
            status_code=404,
            detail="Price record not found"
        )

    await db.delete(price)
    await db.commit()
    await manager.broadcast("prices", {"event": "price.deleted", "price_id": str(price_id)})

    return {
        "message": "Price deleted"
    }
