"""WebSocket channels used by the Cropverse live UI."""
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from config import settings
from redis_manager import redis_manager


class ConnectionManager:
    """Keeps in-memory connections grouped by a named live channel.

    The public ``broadcast`` method publishes through Redis when configured.
    If Redis is unavailable, the manager automatically falls back to local
    process fan-out so local development and single-worker Render deployments
    continue to work without extra services.
    """
    def __init__(self) -> None:
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[channel].add(websocket)

    def disconnect(self, channel: str, websocket: WebSocket) -> None:
        self.connections[channel].discard(websocket)
        if not self.connections[channel]:
            self.connections.pop(channel, None)

    async def broadcast_local(self, channel: str, event: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for websocket in list(self.connections.get(channel, set())):
            try:
                await websocket.send_json(event)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(channel, websocket)

    async def broadcast(self, channel: str, event: dict[str, Any]) -> None:
        if not await redis_manager.publish(channel, event):
            await self.broadcast_local(channel, event)


manager = ConnectionManager()
router = APIRouter(tags=["WebSockets"])


async def _listen(channel: str, websocket: WebSocket) -> None:
    await manager.connect(channel, websocket)
    try:
        while True:
            # Keeps proxies and the client connection alive; clients may send pings.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(channel, websocket)


@router.websocket("/ws/notifications/{user_id}")
async def notification_socket(websocket: WebSocket, user_id: str):
    """Only the JWT owner may subscribe to an individual notification stream."""
    try:
        token = websocket.query_params.get("token")
        subject = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]).get("sub") if token else None
        if subject != user_id:
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return
    await _listen(f"notifications:{user_id}", websocket)


@router.websocket("/ws/prices")
async def price_socket(websocket: WebSocket):
    await _listen("prices", websocket)


@router.websocket("/ws/marketplace")
async def marketplace_socket(websocket: WebSocket):
    await _listen("marketplace", websocket)


@router.websocket("/ws/supply-demand")
async def supply_demand_socket(websocket: WebSocket):
    await _listen("supply-demand", websocket)
