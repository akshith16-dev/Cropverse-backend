from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    get_current_user,
    verify_password,
    hash_password,
)
from db import get_db
from models import (
    User,
    Farmer,
    Shop,
    UserRole,
)

router = APIRouter(
    prefix="/profile",
    tags=["Profile"],
)


# =========================
# Schemas
# =========================

class UpdateProfile(BaseModel):
    name: str
    phone: Optional[str] = None

    # Farmer fields
    village: Optional[str] = None
    district: Optional[str] = None
    soil_type: Optional[str] = None
    land_acres: Optional[float] = None

    # Shop fields
    shop_name: Optional[str] = None
    location: Optional[str] = None


class ChangePassword(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if len(value) < 8 or not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
            raise ValueError("Password must be at least 8 characters and include letters and numbers.")
        return value


# =========================
# Get Profile
# =========================

@router.get("/me")
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = {
        "id": str(current_user.id),
        "name": current_user.name,
        "email": current_user.email,
        "phone": current_user.phone,
        "role": current_user.role,
        "created_at": getattr(
            current_user,
            "created_at",
            None,
        ),
        "last_login": getattr(
            current_user,
            "last_login",
            None,
        ),
    }

    if current_user.role == UserRole.farmer:
        result = await db.execute(
            select(Farmer).where(
                Farmer.user_id == current_user.id
            )
        )

        farmer = result.scalar_one_or_none()

        if farmer:
            profile.update({
                "village": farmer.village,
                "district": farmer.district,
                "soil_type": farmer.soil_type,
                "land_acres": farmer.land_acres,
            })

    elif current_user.role == UserRole.shop:
        result = await db.execute(
            select(Shop).where(
                Shop.user_id == current_user.id
            )
        )

        shop = result.scalar_one_or_none()

        if shop:
            profile.update({
                "shop_name": shop.shop_name,
                "location": shop.location,
            })

    return profile


# =========================
# Update Profile
# =========================

@router.put("/me")
async def update_profile(
    data: UpdateProfile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.name = " ".join(data.name.strip().split())
    current_user.phone = data.phone

    if current_user.role == UserRole.farmer:
        result = await db.execute(
            select(Farmer).where(
                Farmer.user_id == current_user.id
            )
        )

        farmer = result.scalar_one_or_none()

        if farmer:
            if data.village is not None:
                farmer.village = data.village
            if data.district is not None:
                farmer.district = data.district
            if data.soil_type is not None:
                farmer.soil_type = data.soil_type
            if data.land_acres is not None:
                farmer.land_acres = data.land_acres

    elif current_user.role == UserRole.shop:
        result = await db.execute(
            select(Shop).where(
                Shop.user_id == current_user.id
            )
        )

        shop = result.scalar_one_or_none()

        if shop:
            if data.shop_name is not None:
                shop.shop_name = data.shop_name
            if data.location is not None:
                shop.location = data.location

    await db.commit()
    await db.refresh(current_user)

    return await get_profile(
        current_user=current_user,
        db=db,
    )


# =========================
# Change Password
# =========================

@router.put("/change-password")
async def change_password(
    data: ChangePassword,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(
        data.current_password,
        current_user.password_hash,
    ):
        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect",
        )

    current_user.password_hash = hash_password(
        data.new_password
    )

    await db.commit()

    return {
        "message":
            "Password updated successfully"
    }
