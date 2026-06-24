from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from auth import get_current_user

from models import (
    Order,
    Shop,
    BabyCrop,
    CropAssignment,
    Farmer,
    Crop,
    OrderStatus,
    OrderType,
    UserRole
)
from notification_service import create_notification, notify_role
from websocket import manager

router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)


# =====================
# SCHEMAS
# =====================

class OrderCreate(BaseModel):
    baby_crop_id: UUID
    quantity_kg: float = Field(gt=0)
    price_per_kg: float = Field(gt=0)
    order_type: OrderType


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


async def _get_order_or_404(db: AsyncSession, order_id: UUID) -> Order:
    order = await db.scalar(select(Order).where(Order.id == order_id))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


async def _get_shop_for_user(db: AsyncSession, user_id: UUID) -> Shop:
    shop = await db.scalar(select(Shop).where(Shop.user_id == user_id))
    if not shop:
        raise HTTPException(status_code=404, detail="Shop profile not found")
    return shop


async def _get_farmer_for_user(db: AsyncSession, user_id: UUID) -> Farmer:
    farmer = await db.scalar(select(Farmer).where(Farmer.user_id == user_id))
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer profile not found")
    return farmer


async def _get_farmer_order_context(
    db: AsyncSession,
    order_id: UUID,
    user_id: UUID,
) -> tuple[Order, Farmer, Crop, Shop]:
    result = await db.execute(
        select(Order, Farmer, Crop, Shop)
        .join(BabyCrop, Order.baby_crop_id == BabyCrop.id)
        .join(CropAssignment, BabyCrop.assignment_id == CropAssignment.id)
        .join(Farmer, CropAssignment.farmer_id == Farmer.id)
        .join(Crop, CropAssignment.crop_id == Crop.id)
        .join(Shop, Order.shop_id == Shop.id)
        .where(Order.id == order_id, Farmer.user_id == user_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=403, detail="Not allowed")
    return row


async def _notify_order_status(
    db: AsyncSession,
    order: Order,
    shop: Shop,
    farmer: Farmer,
    crop: Crop,
    notification_type: str,
) -> None:
    await create_notification(
        db,
        shop.user_id,
        f"Your order for {crop.crop_name} is now {order.status.value}.",
        notification_type,
    )
    await create_notification(
        db,
        farmer.user_id,
        f"Order {order.status.value}: {order.quantity_kg} kg of {crop.crop_name}.",
        notification_type,
    )


async def _broadcast_order(order: Order, event: str) -> None:
    payload = {
        "event": event,
        "order": {
            "id": str(order.id),
            "baby_crop_id": str(order.baby_crop_id),
            "quantity_kg": order.quantity_kg,
            "status": order.status.value,
        },
    }
    await manager.broadcast("marketplace", payload)


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

    shop = await _get_shop_for_user(db, current_user.id)

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

    available_quantity = crop.quantity_kg or 0
    if data.quantity_kg > available_quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Requested quantity exceeds available stock ({available_quantity} kg)",
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
    crop.quantity_kg = available_quantity - data.quantity_kg

    await db.flush()
    await db.refresh(order)
    crop_owner_result = await db.execute(
        select(Farmer, CropAssignment, Crop)
        .join(CropAssignment, Farmer.id == CropAssignment.farmer_id)
        .join(Crop, CropAssignment.crop_id == Crop.id)
        .where(CropAssignment.id == crop.assignment_id)
    )
    crop_owner = crop_owner_result.one_or_none()
    crop_name = "crop"
    if crop_owner:
        farmer, assignment, order_crop = crop_owner
        crop_name = order_crop.crop_name
        await create_notification(
            db,
            farmer.user_id,
            f"{current_user.name} ordered {order.quantity_kg} kg of your {crop_name}.",
            "order.created",
        )
    await create_notification(
        db,
        current_user.id,
        f"Your order for {order.quantity_kg} kg of {crop_name} was placed.",
        "order.created",
    )
    await notify_role(
        db,
        UserRole.admin,
        f"{current_user.name} placed an order for {order.quantity_kg} kg of {crop_name}.",
        "order.created",
    )
    await db.commit()

    await _broadcast_order(order, "order.created")

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
    if current_user.role == UserRole.farmer:
        farmer = await _get_farmer_for_user(db, current_user.id)

        result = await db.execute(
            select(Order)
            .join(BabyCrop, Order.baby_crop_id == BabyCrop.id)
            .join(CropAssignment, BabyCrop.assignment_id == CropAssignment.id)
            .where(CropAssignment.farmer_id == farmer.id)
        )
        return result.scalars().all()

    if current_user.role != UserRole.shop:
        raise HTTPException(status_code=403, detail="Shops or farmers only")

    shop = await _get_shop_for_user(db, current_user.id)

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
    order = await _get_order_or_404(db, order_id)

    if current_user.role == UserRole.shop:
        shop = await _get_shop_for_user(db, current_user.id)
        if not shop or order.shop_id != shop.id:
            raise HTTPException(status_code=403, detail="Not allowed")
    elif current_user.role == UserRole.farmer:
        await _get_farmer_order_context(db, order_id, current_user.id)
    elif current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Not allowed")

    return order


async def _farmer_transition_order(
    order_id: UUID,
    target_status: OrderStatus,
    allowed_current: set[OrderStatus],
    event: str,
    notification_type: str,
    db: AsyncSession,
    current_user,
):
    if current_user.role != UserRole.farmer:
        raise HTTPException(status_code=403, detail="Farmers only")

    order, farmer, crop, shop = await _get_farmer_order_context(db, order_id, current_user.id)
    if order.status not in allowed_current:
        allowed = ", ".join(status.value for status in allowed_current)
        raise HTTPException(status_code=400, detail=f"Order must be {allowed}")

    if target_status == OrderStatus.rejected:
        baby_crop = await db.scalar(select(BabyCrop).where(BabyCrop.id == order.baby_crop_id))
        if baby_crop:
            baby_crop.quantity_kg = (baby_crop.quantity_kg or 0) + order.quantity_kg

    order.status = target_status
    await db.flush()
    await db.refresh(order)
    await _notify_order_status(db, order, shop, farmer, crop, notification_type)
    await db.commit()
    await _broadcast_order(order, event)

    return {"message": f"Order {target_status.value}", "order": order}


@router.put("/{order_id}/accept")
async def accept_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await _farmer_transition_order(
        order_id,
        OrderStatus.confirmed,
        {OrderStatus.pending},
        "order.accepted",
        "order.accepted",
        db,
        current_user,
    )


@router.put("/{order_id}/reject")
async def reject_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await _farmer_transition_order(
        order_id,
        OrderStatus.rejected,
        {OrderStatus.pending},
        "order.rejected",
        "order.rejected",
        db,
        current_user,
    )


@router.put("/{order_id}/dispatch")
async def dispatch_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await _farmer_transition_order(
        order_id,
        OrderStatus.dispatched,
        {OrderStatus.confirmed},
        "order.dispatched",
        "order.dispatched",
        db,
        current_user,
    )


@router.put("/{order_id}/deliver")
async def deliver_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await _farmer_transition_order(
        order_id,
        OrderStatus.delivered,
        {OrderStatus.dispatched},
        "order.delivered",
        "order.delivered",
        db,
        current_user,
    )


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

    order = await _get_order_or_404(db, order_id)

    previous_status = order.status
    order.status = data.status
    if previous_status != OrderStatus.cancelled and data.status == OrderStatus.cancelled:
        crop_result = await db.execute(select(BabyCrop).where(BabyCrop.id == order.baby_crop_id))
        crop = crop_result.scalar_one_or_none()
        if crop:
            crop.quantity_kg = (crop.quantity_kg or 0) + order.quantity_kg

    shop_result = await db.execute(select(Shop).where(Shop.id == order.shop_id))
    shop = shop_result.scalar_one_or_none()
    owner_result = await db.execute(
        select(Farmer, Crop)
        .join(CropAssignment, Farmer.id == CropAssignment.farmer_id)
        .join(BabyCrop, BabyCrop.assignment_id == CropAssignment.id)
        .join(Crop, CropAssignment.crop_id == Crop.id)
        .where(BabyCrop.id == order.baby_crop_id)
    )
    owner = owner_result.one_or_none()
    if owner:
        farmer, crop = owner
        if shop:
            await _notify_order_status(db, order, shop, farmer, crop, "order.updated")
    await db.flush()
    await db.refresh(order)
    await db.commit()

    await _broadcast_order(order, "order.updated")

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

    crop_result = await db.execute(select(BabyCrop).where(BabyCrop.id == order.baby_crop_id))
    crop = crop_result.scalar_one_or_none()
    if crop and order.status != OrderStatus.cancelled:
        crop.quantity_kg = (crop.quantity_kg or 0) + order.quantity_kg

    await db.delete(order)
    await db.commit()

    return {
        "message": "Order deleted"
    }
