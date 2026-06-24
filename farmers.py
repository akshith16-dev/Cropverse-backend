from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID

from db import get_db
from models import Farmer, User, UserRole
from auth import get_current_user, require_admin

router = APIRouter(prefix="/farmers", tags=["Farmers"])


# ─── Schemas ──────────────────────────────

class FarmerResponse(BaseModel):
    id:         UUID
    user_id:    UUID
    village:    str
    district:   str
    soil_type:  str
    land_acres: float
    micro_zone: Optional[str] = None
    latitude:   Optional[float] = None
    longitude:  Optional[float] = None
    name:       str
    email:      str
    phone:      Optional[str] = None

    class Config:
        from_attributes = True

class UpdateFarmer(BaseModel):
    micro_zone: Optional[str] = None
    latitude:   Optional[float] = None
    longitude:  Optional[float] = None
    soil_type:  Optional[str] = None
    land_acres: Optional[float] = Field(default=None, gt=0)


# ─── Get all farmers (admin only) ─────────

@router.get("/", response_model=List[FarmerResponse])
async def get_all_farmers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    result = await db.execute(
        select(Farmer, User)
        .join(User, Farmer.user_id == User.id)
    )
    rows = result.all()

    farmers = []
    for farmer, user in rows:
        farmers.append(FarmerResponse(
            id=farmer.id,
            user_id=farmer.user_id,
            village=farmer.village,
            district=farmer.district,
            soil_type=farmer.soil_type,
            land_acres=farmer.land_acres,
            micro_zone=farmer.micro_zone,
            latitude=farmer.latitude,
            longitude=farmer.longitude,
            name=user.name,
            email=user.email,
            phone=user.phone,
        ))
    return farmers


# ─── Get farmers by district (admin only) ─

@router.get("/district/{district}", response_model=List[FarmerResponse])
async def get_farmers_by_district(
    district: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    result = await db.execute(
        select(Farmer, User)
        .join(User, Farmer.user_id == User.id)
        .where(Farmer.district == district)
    )
    rows = result.all()

    farmers = []
    for farmer, user in rows:
        farmers.append(FarmerResponse(
            id=farmer.id,
            user_id=farmer.user_id,
            village=farmer.village,
            district=farmer.district,
            soil_type=farmer.soil_type,
            land_acres=farmer.land_acres,
            micro_zone=farmer.micro_zone,
            latitude=farmer.latitude,
            longitude=farmer.longitude,
            name=user.name,
            email=user.email,
            phone=user.phone,
        ))
    return farmers


# ─── Get my profile (farmer only) ─────────

@router.get("/me", response_model=FarmerResponse)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.farmer:
        raise HTTPException(status_code=403, detail="Farmers only")

    result = await db.execute(
        select(Farmer).where(Farmer.user_id == current_user.id)
    )
    farmer = result.scalar_one_or_none()

    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer profile not found")

    return FarmerResponse(
        id=farmer.id,
        user_id=farmer.user_id,
        village=farmer.village,
        district=farmer.district,
        soil_type=farmer.soil_type,
        land_acres=farmer.land_acres,
        micro_zone=farmer.micro_zone,
        latitude=farmer.latitude,
        longitude=farmer.longitude,
        name=current_user.name,
        email=current_user.email,
        phone=current_user.phone,
    )


# ─── Update farmer (admin only) ───────────

@router.put("/{farmer_id}", response_model=FarmerResponse)
async def update_farmer(
    farmer_id: UUID,
    data: UpdateFarmer,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    result = await db.execute(
        select(Farmer, User)
        .join(User, Farmer.user_id == User.id)
        .where(Farmer.id == farmer_id)
    )
    row = result.one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Farmer not found")

    farmer, user = row

    if data.micro_zone  is not None: farmer.micro_zone  = data.micro_zone
    if data.latitude    is not None: farmer.latitude    = data.latitude
    if data.longitude   is not None: farmer.longitude   = data.longitude
    if data.soil_type   is not None: farmer.soil_type   = data.soil_type
    if data.land_acres  is not None: farmer.land_acres  = data.land_acres

    await db.commit()

    return FarmerResponse(
        id=farmer.id,
        user_id=farmer.user_id,
        village=farmer.village,
        district=farmer.district,
        soil_type=farmer.soil_type,
        land_acres=farmer.land_acres,
        micro_zone=farmer.micro_zone,
        latitude=farmer.latitude,
        longitude=farmer.longitude,
        name=user.name,
        email=user.email,
        phone=user.phone,
    )


# ─── Delete farmer (admin only) ───────────

@router.delete("/{farmer_id}")
async def delete_farmer(
    farmer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    result = await db.execute(
        select(Farmer).where(Farmer.id == farmer_id)
    )
    farmer = result.scalar_one_or_none()

    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")

    await db.delete(farmer)
    await db.commit()

    return {"message": "Farmer deleted successfully"}
