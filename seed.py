"""Development-only seed data.

Run from ``cbackend`` after setting .env: ``python seed.py``.
It is idempotent and deliberately does not create users or passwords.
"""
import asyncio
from sqlalchemy import select
from db import AsyncSessionLocal, engine, Base
from models import Crop

CROPS = [
    {"crop_name": "Rice", "season": "kharif", "soil_suitability": "clay, alluvial", "avg_yield_per_acre": 2400, "min_price": 18, "max_price": 32, "cultivation_cost": 28000},
    {"crop_name": "Maize", "season": "kharif", "soil_suitability": "loamy, red", "avg_yield_per_acre": 1800, "min_price": 16, "max_price": 28, "cultivation_cost": 22000},
    {"crop_name": "Groundnut", "season": "rabi", "soil_suitability": "red, sandy", "avg_yield_per_acre": 900, "min_price": 45, "max_price": 75, "cultivation_cost": 26000},
    {"crop_name": "Cotton", "season": "kharif", "soil_suitability": "black", "avg_yield_per_acre": 700, "min_price": 50, "max_price": 85, "cultivation_cost": 35000},
]

async def seed() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        existing = set((await session.execute(select(Crop.crop_name))).scalars())
        session.add_all(Crop(**item) for item in CROPS if item["crop_name"] not in existing)
        await session.commit()
    print("Seeded baseline Cropverse crops.")

if __name__ == "__main__":
    asyncio.run(seed())
