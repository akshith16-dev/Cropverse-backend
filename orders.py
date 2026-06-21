from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from auth import get_current_user

from models import (
    Order,
    Shop,
    BabyCrop,
    OrderStatus,
    OrderType,
    UserRole
)

router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)


# =====================
# SCHEMAS
# =====================

class OrderCreate(BaseModel):
    baby_crop_id: UUID
    quantity_kg: float
    price_per_kg: float
    order_type: OrderType


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


# =====================
# CREATE ORDER
# =====================

@router.post("/")
async def create_order(
    data: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role != UserRole.shop:
        raise HTTPException(
            status_code=403,
            detail="Only shops can place orders"
        )

    shop_result = await db.execute(
        select(Shop).where(
            Shop.user_id == current_user.id
        )
    )

    shop = shop_result.scalar_one_or_none()

    if not shop:
        raise HTTPException(
            status_code=404,
            detail="Shop profile not found"
        )

    crop_result = await db.execute(
        select(BabyCrop).where(
            BabyCrop.id == data.baby_crop_id
        )
    )

    crop = crop_result.scalar_one_or_none()

    if not crop:
        raise HTTPException(
            status_code=404,
            detail="Baby crop not found"
        )

    order = Order(
        shop_id=shop.id,
        baby_crop_id=data.baby_crop_id,
        quantity_kg=data.quantity_kg,
        price_per_kg=data.price_per_kg,
        order_type=data.order_type,
        status=OrderStatus.pending
    )

    db.add(order)

    await db.flush()
    await db.refresh(order)
    await db.commit()

    return {
        "message": "Order created",
        "order": order
    }


# =====================
# ADMIN ALL ORDERS
# =====================

@router.get("/")
async def get_all_orders(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=403,
            detail="Admins only"
        )

    result = await db.execute(
        select(Order)
    )

    return result.scalars().all()


# =====================
# MY ORDERS
# =====================

@router.get("/me")
async def get_my_orders(
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
        select(Order).where(
            Order.shop_id == shop.id
        )
    )

    return result.scalars().all()


# =====================
# SINGLE ORDER
# =====================

@router.get("/{order_id}")
async def get_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    result = await db.execute(
        select(Order).where(
            Order.id == order_id
        )
    )

    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    return order


# =====================
# UPDATE STATUS
# =====================

@router.put("/{order_id}/status")
async def update_order_status(
    order_id: UUID,
    data: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=403,
            detail="Admins only"
        )

    result = await db.execute(
        select(Order).where(
            Order.id == order_id
        )
    )

    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    order.status = data.status

    await db.flush()
    await db.refresh(order)
    await db.commit()

    return {
        "message": "Order status updated",
        "order": order
    }


# =====================
# DELETE ORDER
# =====================

@router.delete("/{order_id}")
async def delete_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=403,
            detail="Admins only"
        )

    result = await db.execute(
        select(Order).where(
            Order.id == order_id
        )
    )

    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    await db.delete(order)
    await db.commit()

    return {
        "message": "Order deleted"
    }
