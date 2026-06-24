from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from auth import get_current_user
from models import Notification, User, UserRole
from notification_service import create_notification as persist_notification

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"]
)
class NotificationCreate(BaseModel):
    user_id: UUID
    message: str
    type: str


class NotificationResponse(BaseModel):
    id: UUID
    message: str
    type: str
    is_read: bool

    class Config:
        from_attributes = True
@router.post("/")
async def create_notification(
    data: NotificationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.admin and data.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to create notifications for another user")

    await persist_notification(db, data.user_id, data.message, data.type)
    await db.commit()

    return {
        "message": "Notification created"
    }
@router.get("/")
async def get_my_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.sent_at.desc())
    )

    return result.scalars().all()
@router.put("/{notification_id}/read")
async def mark_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Notification)
        .where(Notification.id == notification_id)
    )

    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(
            status_code=404,
            detail="Notification not found"
        )

    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not allowed"
        )

    notification.is_read = True

    await db.commit()

    return {
        "message": "Notification marked as read"
    }
