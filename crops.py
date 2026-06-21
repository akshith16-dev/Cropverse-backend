from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID

from db import get_db
from models import Crop
from auth import require_admin, get_current_user

router = APIRouter(prefix="/crops", tags=["Crops"])


# ─── Schemas ──────────────────────────────

class CropCreate(BaseModel):
    crop_name:          str
    season:             str
    soil_suitability:   str
    avg_yield_per_acre: float
    min_price:          float
    max_price:          float
    cultivation_cost:   float

class CropUpdate(BaseModel):
    season:             Optional[str]   = None
    soil_suitability:   Optional[str]   = None
    avg_yield_per_acre: Optional[float] = None
    min_price:          Optional[float] = None
    max_price:          Optional[float] = None
    cultivation_cost:   Optional[float] = None

class CropResponse(BaseModel):
    id:                 UUID
    crop_name:          str
    season:             str
    soil_suitability:   str
    avg_yield_per_acre: float
    min_price:          float
    max_price:          float
    cultivation_cost:   float
    fair_price:         float   # auto calculated

    class Config:
        from_attributes = True


# ─── Get all crops (everyone) ─────────────

@router.get("/", response_model=List[CropResponse])
async def get_all_crops(
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Crop))
    crops = result.scalars().all()

    return [
        CropResponse(
            id=c.id,
            crop_name=c.crop_name,
            season=c.season,
            soil_suitability=c.soil_suitability,
            avg_yield_per_acre=c.avg_yield_per_acre,
            min_price=c.min_price,
            max_price=c.max_price,
            cultivation_cost=c.cultivation_cost,
            fair_price=round(c.cultivation_cost * 1.2, 2),  # cost + 20%
        )
        for c in crops
    ]


# ─── Get single crop (everyone) ───────────

@router.get("/{crop_id}", response_model=CropResponse)
async def get_crop(
    crop_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Crop).where(Crop.id == crop_id))
    crop = result.scalar_one_or_none()

    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found")

    return CropResponse(
        id=crop.id,
        crop_name=crop.crop_name,
        season=crop.season,
        soil_suitability=crop.soil_suitability,
        avg_yield_per_acre=crop.avg_yield_per_acre,
        min_price=crop.min_price,
        max_price=crop.max_price,
        cultivation_cost=crop.cultivation_cost,
        fair_price=round(crop.cultivation_cost * 1.2, 2),
    )


# ─── Add crop (admin only) ────────────────

@router.post("/", response_model=CropResponse, status_code=201)
async def add_crop(
    data: CropCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin)
):
    # check duplicate
    result = await db.execute(
        select(Crop).where(Crop.crop_name == data.crop_name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Crop already exists")

    crop = Crop(
        crop_name=data.crop_name,
        season=data.season,
        soil_suitability=data.soil_suitability,
        avg_yield_per_acre=data.avg_yield_per_acre,
        min_price=data.min_price,
        max_price=data.max_price,
        cultivation_cost=data.cultivation_cost,
    )
    db.add(crop)
    await db.commit()
    await db.refresh(crop)

    return CropResponse(
        id=crop.id,
        crop_name=crop.crop_name,
        season=crop.season,
        soil_suitability=crop.soil_suitability,
        avg_yield_per_acre=crop.avg_yield_per_acre,
        min_price=crop.min_price,
        max_price=crop.max_price,
        cultivation_cost=crop.cultivation_cost,
        fair_price=round(crop.cultivation_cost * 1.2, 2),
    )


# ─── Update crop (admin only) ─────────────

@router.put("/{crop_id}", response_model=CropResponse)
async def update_crop(
    crop_id: UUID,
    data: CropUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin)
):
    result = await db.execute(select(Crop).where(Crop.id == crop_id))
    crop = result.scalar_one_or_none()

    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found")

    if data.season             is not None: crop.season             = data.season
    if data.soil_suitability   is not None: crop.soil_suitability   = data.soil_suitability
    if data.avg_yield_per_acre is not None: crop.avg_yield_per_acre = data.avg_yield_per_acre
    if data.min_price          is not None: crop.min_price          = data.min_price
    if data.max_price          is not None: crop.max_price          = data.max_price
    if data.cultivation_cost   is not None: crop.cultivation_cost   = data.cultivation_cost

    await db.commit()
    await db.refresh(crop)

    return CropResponse(
        id=crop.id,
        crop_name=crop.crop_name,
        season=crop.season,
        soil_suitability=crop.soil_suitability,
        avg_yield_per_acre=crop.avg_yield_per_acre,
        min_price=crop.min_price,
        max_price=crop.max_price,
        cultivation_cost=crop.cultivation_cost,
        fair_price=round(crop.cultivation_cost * 1.2, 2),
    )


# ─── Delete crop (admin only) ─────────────

@router.delete("/{crop_id}")
async def delete_crop(
    crop_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin)
):
    result = await db.execute(select(Crop).where(Crop.id == crop_id))
    crop = result.scalar_one_or_none()

    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found")

    await db.delete(crop)
    await db.commit()

    return {"message": f"{crop.crop_name} deleted successfully"}