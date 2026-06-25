import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

import farmers
from config import settings
from db import engine, Base
from exceptions import register_exception_handlers
from logging_config import configure_logging
from redis_manager import redis_manager
import auth
import crops
import assignments
import baby_crops
import demand
import orders
import prices
import shops
import notifications
import chatbot
import websocket
import ai
import ai_planning
import analytics
import reports
import uploads
from uploads import UPLOAD_DIR
from profile import router as profile_router

logger = configure_logging(settings.DEBUG)
STARTED_AT = datetime.now(timezone.utc)

@asynccontextmanager
async def lifespan(app: FastAPI):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await redis_manager.start(websocket.manager.broadcast_local)
    yield
    await redis_manager.stop()
    await engine.dispose()

app = FastAPI(
    title=settings.APP_NAME,
    description="The Complete Universe of Smart Agriculture",
    version="1.0.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

try:
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=429,
            content={"success": False, "message": "Too many requests", "details": str(exc.detail)},
        )

    app.add_middleware(SlowAPIMiddleware)
except Exception as exc:
    logging.getLogger("cropverse").warning("SlowAPI unavailable; rate limiting disabled: %s", exc)

@app.middleware("http")
async def request_logging_and_security_headers(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info("%s %s -> %s %.2fms", request.method, request.url.path, response.status_code, elapsed_ms)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not settings.DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router) 
app.include_router(farmers.router)
app.include_router(crops.router)
app.include_router(assignments.router)
app.include_router(baby_crops.router)
app.include_router(demand.router)
app.include_router(orders.router)
app.include_router(prices.router)
app.include_router(shops.router)
app.include_router(notifications.router)
app.include_router(chatbot.router)
app.include_router(profile_router)
app.include_router(websocket.router)
app.include_router(ai.router)
app.include_router(ai_planning.router)
app.include_router(analytics.router)
app.include_router(reports.router)
app.include_router(uploads.router)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "app": settings.APP_NAME}

@app.get("/health", tags=["Health"])
async def health_check():
    """Render-friendly liveness/readiness check."""
    db_status = "healthy"
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {exc.__class__.__name__}"
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "app": settings.APP_NAME,
        "database": db_status,
        "redis": "connected" if redis_manager.available else "disabled_or_unavailable",
        "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
    }

@app.get("/health/db", tags=["Health"])
async def database_health_check():
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "healthy", "database": "ok"}

@app.get("/health/redis", tags=["Health"])
async def redis_health_check():
    return {"status": "healthy" if redis_manager.available else "disabled_or_unavailable"}
