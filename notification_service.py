from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Notification, User, UserRole
from websocket import manager


async def create_notification(
    db: AsyncSession,
    user_id: UUID,
    message: str,
    notification_type: str,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        message=message,
        type=notification_type,
    )
    db.add(notification)
    await db.flush()
    await db.refresh(notification)
    await manager.broadcast(
        f"notifications:{notification.user_id}",
        {
            "event": "notification.created",
            "notification": {
                "id": str(notification.id),
                "message": notification.message,
                "type": notification.type,
                "is_read": notification.is_read,
                "sent_at": notification.sent_at.isoformat(),
            },
        },
    )
    return notification


async def notify_role(
    db: AsyncSession,
    role: UserRole,
    message: str,
    notification_type: str,
) -> None:
    result = await db.execute(select(User.id).where(User.role == role))
    for user_id in result.scalars().all():
        await create_notification(db, user_id, message, notification_type)


async def notify_all(
    db: AsyncSession,
    message: str,
    notification_type: str,
) -> None:
    result = await db.execute(select(User.id))
    for user_id in result.scalars().all():
        await create_notification(db, user_id, message, notification_type)
