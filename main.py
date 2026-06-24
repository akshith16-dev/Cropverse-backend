from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import farmers
from config import settings
from db import engine, Base
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
from profile import router as profile_router
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title=settings.APP_NAME,
    description="The Complete Universe of Smart Agriculture",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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
@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "app": settings.APP_NAME}