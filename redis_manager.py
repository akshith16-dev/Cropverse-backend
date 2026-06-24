"""Optional Redis Pub/Sub fan-out with a no-Redis local fallback."""
import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from config import settings

logger = logging.getLogger("cropverse")
MessageHandler = Callable[[str, dict[str, Any]], Awaitable[None]]

class RedisPubSubManager:
    def __init__(self) -> None:
        self.client = None
        self.listener_task: asyncio.Task | None = None
        self.handler: MessageHandler | None = None
        self.available = False

    async def start(self, handler: MessageHandler) -> None:
        self.handler = handler
        if not settings.REDIS_URL:
            return
        try:
            import redis.asyncio as redis
            self.client = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)
            await self.client.ping()
            self.available = True
            self.listener_task = asyncio.create_task(self._listen())
            logger.info("Redis Pub/Sub connected")
        except Exception as exc:
            self.available = False
            self.client = None
            logger.warning("Redis unavailable; using local WebSocket events: %s", exc)

    async def _listen(self) -> None:
        if not self.client:
            return
        try:
            pubsub = self.client.pubsub()
            await pubsub.psubscribe("notifications:*", "prices", "marketplace", "supply-demand")
            async for message in pubsub.listen():
                if message.get("type") not in {"message", "pmessage"}:
                    continue
                try:
                    payload = json.loads(message["data"])
                    channel = str(message.get("channel") or "")
                    if self.handler:
                        await self.handler(channel, payload)
                except (TypeError, json.JSONDecodeError) as exc:
                    logger.warning("Ignored invalid Redis event: %s", exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.available = False
            logger.warning("Redis subscriber stopped; using local events: %s", exc)

    async def publish(self, channel: str, event: dict[str, Any]) -> bool:
        if not self.available or not self.client:
            return False
        try:
            await self.client.publish(channel, json.dumps(event, default=str))
            return True
        except Exception as exc:
            self.available = False
            logger.warning("Redis publish failed; using local event: %s", exc)
            return False

    async def stop(self) -> None:
        if self.listener_task:
            self.listener_task.cancel()
            try: await self.listener_task
            except asyncio.CancelledError: pass
        if self.client:
            await self.client.aclose()
        self.listener_task = None; self.client = None; self.available = False

redis_manager = RedisPubSubManager()
