"""Prediction APIs. Historical platform data is used where it is available."""
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from db import get_db
from ml.crop_predictor import recommend
from models import Crop, DemandRequest, MarketPrice

router = APIRouter(prefix="/ai", tags=["AI & Predictions"])

class CropRecommendationRequest(BaseModel):
    soil_type: str = Field(min_length=2, max_length=50)
    district: str = Field(min_length=2, max_length=100)
    season: str = Field(min_length=2, max_length=50)
    land_acres: float = Field(gt=0, le=10000)

class ForecastRequest(BaseModel):
    crop_id: str
    days: Literal[30, 90] = 30

@router.post("/recommend-crop")
async def recommend_crop(data: CropRecommendationRequest, _=Depends(get_current_user)):
    return recommend(**data.model_dump())

def _linear_forecast(values: list[float], days: int, label: str) -> list[dict]:
    """A deterministic fallback when a short history cannot fit Prophet."""
    baseline = sum(values) / len(values) if values else 0
    change = (values[-1] - values[0]) / max(len(values) - 1, 1) if len(values) > 1 else 0
    return [{"date": (datetime.utcnow() + timedelta(days=step)).date().isoformat(), label: round(max(0, baseline + change * step), 2)} for step in range(1, days + 1)]

def _prophet_forecast(points: list[tuple[datetime, float]], days: int, label: str) -> tuple[str, list[dict]]:
    """Use Prophet when enough dated observations exist, otherwise stay useful."""
    if len(points) < 3:
        return "baseline", _linear_forecast([value for _, value in points], days, label)
    try:
        import pandas as pd
        from prophet import Prophet
        frame = pd.DataFrame(points, columns=["ds", "y"])
        model = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=False)
        model.fit(frame)
        future = model.make_future_dataframe(periods=days)
        predicted = model.predict(future).tail(days)
        return "prophet", [{"date": row.ds.date().isoformat(), label: round(max(0, float(row.yhat)), 2)} for row in predicted.itertuples()]
    except (ImportError, ValueError, TypeError):
        return "baseline", _linear_forecast([value for _, value in points], days, label)

@router.post("/predict-demand")
async def predict_demand(data: ForecastRequest, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    crop = await db.scalar(select(Crop).where(Crop.id == data.crop_id))
    if not crop:
        raise HTTPException(404, "Crop not found")
    rows = (await db.execute(select(DemandRequest).where(DemandRequest.crop_id == data.crop_id).order_by(desc(DemandRequest.created_at)))).scalars().all()
    # Demand requests are events, so their quantities are useful even when sparse.
    method, forecast = _prophet_forecast([(row.created_at, row.quantity_kg) for row in reversed(rows)], data.days, "predicted_quantity_kg")
    return {"crop": crop.crop_name, "days": data.days, "method": method, "forecast": forecast}

@router.post("/predict-price")
async def predict_price(data: ForecastRequest, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    crop = await db.scalar(select(Crop).where(Crop.id == data.crop_id))
    if not crop:
        raise HTTPException(404, "Crop not found")
    rows = (await db.execute(select(MarketPrice).where(MarketPrice.crop_id == data.crop_id).order_by(MarketPrice.recorded_at))).scalars().all()
    points = [(row.recorded_at, row.price_per_kg) for row in rows] or [(datetime.utcnow(), (crop.min_price + crop.max_price) / 2)]
    method, forecast = _prophet_forecast(points, data.days, "predicted_price_per_kg")
    return {"crop": crop.crop_name, "days": data.days, "method": method, "forecast": forecast}
