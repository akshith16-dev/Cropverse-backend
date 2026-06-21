from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID

from db import get_db
from models import Shop, User
from auth import require_admin

router = APIRouter(prefix="/shops", tags=["Shops"])


# ─── Schemas ──────────────────────────────

class ShopResponse(BaseModel):
    id: UUID
    user_id: UUID
    shop_name: str
    location: str
    contact: Optional[str] = None
    name: str
    email: str
    phone: Optional[str] = None

    class Config:
        from_attributes = True


# ─── Get all shops (admin only) ───────────

@router.get("/", response_model=List[ShopResponse])
async def get_all_shops(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(
        select(Shop, User)
        .join(User, Shop.user_id == User.id)
    )
    rows = result.all()

    shops = []
    for shop, user in rows:
        shops.append(
            ShopResponse(
                id=shop.id,
                user_id=shop.user_id,
                shop_name=shop.shop_name,
                location=shop.location,
                contact=shop.contact,
                name=user.name,
                email=user.email,
                phone=user.phone,
            )
        )

    return shops


# ─── Get single shop ──────────────────────

@router.get("/{shop_id}", response_model=ShopResponse)
async def get_shop(
    shop_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(
        select(Shop, User)
        .join(User, Shop.user_id == User.id)
        .where(Shop.id == shop_id)
    )
    row = result.one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Shop not found")

    shop, user = row

    return ShopResponse(
        id=shop.id,
        user_id=shop.user_id,
        shop_name=shop.shop_name,
        location=shop.location,
        contact=shop.contact,
        name=user.name,
        email=user.email,
        phone=user.phone,
    )
