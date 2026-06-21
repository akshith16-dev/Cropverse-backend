from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from auth import get_current_user

from models import (
    MarketPrice,
    Crop,
    UserRole
)

router = APIRouter(
    prefix="/prices",
    tags=["Prices"]
)


# =========================
# SCHEMAS
# =========================

class PriceCreate(BaseModel):
    crop_id: UUID
    price_per_kg: float
    fair_price: float
    market_name: str


class PriceUpdate(BaseModel):
    price_per_kg: float | None = None
    fair_price: float | None = None
    market_name: str | None = None


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
    await db.commit()

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

    await db.flush()
    await db.refresh(price)
    await db.commit()

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

    return {
        "message": "Price deleted"
    }
