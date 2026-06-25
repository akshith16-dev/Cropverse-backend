import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from assignments import check_oversupply, generate_xai_explanation
from auth import get_current_user, require_admin
from db import get_db
from models import (
    AssignmentStatus,
    Crop,
    CropAssignment,
    CropRecommendation,
    DemandRequest,
    Farmer,
    MarketPrice,
    User,
    UserRole,
)
from notification_service import create_notification, notify_role
from websocket import manager

router = APIRouter(prefix="/ai", tags=["AI Planning"])


class RecommendationResponse(BaseModel):
    id: UUID | None = None
    farmer_id: UUID
    crop_id: UUID
    crop: str
    next_crop: str | None = None
    recommendation_type: str
    confidence: float
    expected_profit: float
    reasons: list[str]
    created_at: datetime | None = None


class AutoAssignmentResponse(BaseModel):
    assignment_id: UUID
    recommendation: RecommendationResponse
    message: str


@dataclass
class CropSignals:
    demand_kg: float
    latest_demand_at: datetime | None
    price_per_kg: float
    assigned_count: int
    previous_crop_name: str | None


def current_agricultural_season(now: datetime | None = None) -> str:
    month = (now or datetime.utcnow()).month
    if 6 <= month <= 10:
        return "kharif"
    if month in {11, 12, 1, 2, 3}:
        return "rabi"
    return "zaid"


def _contains_token(text: str, token: str) -> bool:
    return token.lower().strip() in (text or "").lower()


def _rotation_bonus(previous_crop: str | None, crop: Crop) -> tuple[float, list[str]]:
    if not previous_crop:
        return 0.04, ["Diversifies historical assignments"]
    previous = previous_crop.lower()
    name = crop.crop_name.lower()
    reasons = []
    score = 0.0
    legumes = {"groundnut", "peanut", "gram", "chickpea", "soybean", "green gram", "black gram", "lentil"}
    cereals = {"rice", "paddy", "wheat", "maize", "corn"}
    previous_is_cereal = any(cereal in previous for cereal in cereals)
    next_is_legume = any(legume in name for legume in legumes)
    if previous_is_cereal and next_is_legume:
        score += 0.18
        reasons.append("Restores soil nitrogen")
    if previous != name:
        score += 0.08
        reasons.append("Rotation compatible")
    else:
        score -= 0.08
    return score, reasons


async def _latest_previous_crop(db: AsyncSession, farmer_id: UUID) -> str | None:
    row = (
        await db.execute(
            select(Crop.crop_name)
            .join(CropAssignment, CropAssignment.crop_id == Crop.id)
            .where(CropAssignment.farmer_id == farmer_id)
            .order_by(desc(CropAssignment.assigned_at))
            .limit(1)
        )
    ).first()
    return row[0] if row else None


async def _signals_for_crop(db: AsyncSession, crop: Crop) -> tuple[float, datetime | None, float, int]:
    demand_row = (
        await db.execute(
            select(func.sum(DemandRequest.quantity_kg), func.max(DemandRequest.created_at)).where(
                DemandRequest.crop_id == crop.id,
                DemandRequest.status.in_(["open", "approved", "planned"]),
            )
        )
    ).one()
    demand = demand_row[0] or 0
    latest_demand_at = demand_row[1]
    latest_price = await db.scalar(
        select(MarketPrice.price_per_kg)
        .where(MarketPrice.crop_id == crop.id)
        .order_by(desc(MarketPrice.recorded_at))
        .limit(1)
    )
    assigned_count = (
        await db.execute(select(func.count(CropAssignment.id)).where(CropAssignment.crop_id == crop.id))
    ).scalar() or 0
    fallback_price = (crop.min_price + crop.max_price) / 2
    return float(demand), latest_demand_at, float(latest_price or fallback_price), int(assigned_count)


async def _rank_crops(
    db: AsyncSession,
    farmer: Farmer,
    recommendation_type: str,
    limit: int = 5,
) -> list[dict]:
    crops = (await db.execute(select(Crop))).scalars().all()
    if not crops:
        return []

    season = current_agricultural_season()
    previous_crop = await _latest_previous_crop(db, farmer.id)
    crop_metrics: dict[UUID, CropSignals] = {}
    max_demand = 1.0
    max_price = 1.0
    for crop in crops:
        demand_kg, latest_demand_at, price_per_kg, assigned_count = await _signals_for_crop(db, crop)
        crop_metrics[crop.id] = CropSignals(demand_kg, latest_demand_at, price_per_kg, assigned_count, previous_crop)
        max_demand = max(max_demand, demand_kg)
        max_price = max(max_price, price_per_kg)

    ranked = []
    for crop in crops:
        signals = crop_metrics[crop.id]
        reasons: list[str] = []
        score = 0.35

        if _contains_token(crop.soil_suitability, farmer.soil_type):
            score += 0.22
            reasons.append("Suitable soil")
        if _contains_token(crop.season, season) or crop.season.lower() in {"all", "year-round", "year round"}:
            score += 0.18
            reasons.append("Season compatible")
        if signals.demand_kg > 0:
            score += 0.16 * (signals.demand_kg / max_demand)
            reasons.append("High demand")
        if signals.price_per_kg >= ((crop.min_price + crop.max_price) / 2):
            score += 0.12 * (signals.price_per_kg / max_price)
            reasons.append("Good market prices")

        rotation_score, rotation_reasons = _rotation_bonus(previous_crop, crop)
        score += rotation_score
        if recommendation_type == "rotation":
            reasons = rotation_reasons + reasons
        else:
            reasons.extend(rotation_reasons)

        expected_revenue = farmer.land_acres * crop.avg_yield_per_acre * signals.price_per_kg
        expected_cost = farmer.land_acres * crop.cultivation_cost
        expected_profit = max(0, expected_revenue - expected_cost)
        if expected_profit > 0:
            score += min(0.12, expected_profit / 1_000_000)
            reasons.append("High expected profit")

        if signals.assigned_count == 0:
            score += 0.03
            reasons.append("Expands crop diversity")

        ranked.append(
            {
                "farmer_id": farmer.id,
                "crop_id": crop.id,
                "crop": crop.crop_name,
                "recommendation_type": recommendation_type,
                "confidence": round(max(0.01, min(score, 0.98)), 2),
                "expected_profit": round(expected_profit, 2),
                "reasons": list(dict.fromkeys(reasons))[:5],
                "_crop": crop,
            }
        )

    return sorted(
        ranked,
        key=lambda item: (
            item["confidence"],
            crop_metrics[item["crop_id"]].demand_kg,
            crop_metrics[item["crop_id"]].latest_demand_at or datetime.min,
            item["expected_profit"],
        ),
        reverse=True,
    )[:limit]


async def save_recommendation(
    db: AsyncSession,
    farmer: Farmer,
    crop: Crop,
    recommendation_type: str,
    confidence: float,
    expected_profit: float,
    reasons: list[str],
) -> CropRecommendation:
    recommendation = CropRecommendation(
        farmer_id=farmer.id,
        crop_id=crop.id,
        recommendation_type=recommendation_type,
        confidence=confidence,
        expected_profit=expected_profit,
        reasons=json.dumps(reasons),
    )
    db.add(recommendation)
    await db.flush()
    await db.refresh(recommendation)
    await create_notification(
        db,
        farmer.user_id,
        f"AI has recommended {crop.crop_name} as your next crop.",
        f"ai.{recommendation_type}.created",
    )
    await notify_role(
        db,
        UserRole.admin,
        f"AI generated a {recommendation_type.replace('_', ' ')} recommendation for {crop.crop_name}.",
        f"ai.{recommendation_type}.created",
    )
    await manager.broadcast(
        "ai-planning",
        {
            "event": f"ai.{recommendation_type}.created",
            "farmer_id": str(farmer.id),
            "crop_id": str(crop.id),
            "crop": crop.crop_name,
            "confidence": confidence,
        },
    )
    return recommendation


def recommendation_payload(recommendation: CropRecommendation, crop: Crop, include_next_crop: bool = False) -> dict:
    try:
        reasons = json.loads(recommendation.reasons or "[]")
    except json.JSONDecodeError:
        reasons = [recommendation.reasons]
    return {
        "id": recommendation.id,
        "farmer_id": recommendation.farmer_id,
        "crop_id": recommendation.crop_id,
        "crop": crop.crop_name,
        "next_crop": crop.crop_name if include_next_crop else None,
        "recommendation_type": recommendation.recommendation_type,
        "confidence": recommendation.confidence,
        "expected_profit": recommendation.expected_profit,
        "reasons": reasons,
        "created_at": recommendation.created_at,
    }


async def generate_and_save_rotation_recommendation(db: AsyncSession, farmer: Farmer) -> CropRecommendation | None:
    ranked = await _rank_crops(db, farmer, "rotation", 1)
    if not ranked:
        return None
    top = ranked[0]
    return await save_recommendation(
        db,
        farmer,
        top["_crop"],
        "rotation",
        top["confidence"],
        top["expected_profit"],
        top["reasons"],
    )


@router.post("/recommend-crops/{farmer_id}", response_model=list[RecommendationResponse])
async def recommend_crops_for_farmer(
    farmer_id: UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    farmer = await db.scalar(select(Farmer).where(Farmer.id == farmer_id))
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")
    ranked = await _rank_crops(db, farmer, "crop_recommendation", 5)
    saved = []
    for item in ranked:
        recommendation = await save_recommendation(
            db,
            farmer,
            item["_crop"],
            "crop_recommendation",
            item["confidence"],
            item["expected_profit"],
            item["reasons"],
        )
        saved.append(recommendation_payload(recommendation, item["_crop"]))
    await db.commit()
    return saved


@router.post("/auto-assign/{farmer_id}", response_model=AutoAssignmentResponse)
async def auto_assign_farmer(
    farmer_id: UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    row = (
        await db.execute(
            select(Farmer, User)
            .join(User, Farmer.user_id == User.id)
            .where(Farmer.id == farmer_id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Farmer not found")
    farmer, farmer_user = row
    ranked = await _rank_crops(db, farmer, "auto_assignment", 1)
    if not ranked:
        raise HTTPException(status_code=400, detail="No crops available for recommendation")
    top = ranked[0]
    crop = top["_crop"]
    season = current_agricultural_season()
    year = datetime.utcnow().year

    duplicate = await db.scalar(
        select(CropAssignment).where(
            CropAssignment.farmer_id == farmer.id,
            CropAssignment.season == season,
            CropAssignment.year == year,
        )
    )
    if duplicate:
        raise HTTPException(status_code=400, detail="Farmer already has a crop assigned for this season")

    total_farmers_this_crop = (
        await db.execute(
            select(func.count(CropAssignment.id)).where(
                CropAssignment.crop_id == crop.id,
                CropAssignment.season == season,
                CropAssignment.year == year,
            )
        )
    ).scalar() or 0
    demand_kg, _, _, _ = await _signals_for_crop(db, crop)
    total_supply_kg = (total_farmers_this_crop + 1) * farmer.land_acres * crop.avg_yield_per_acre
    total_demand_kg = max(demand_kg, total_supply_kg * 0.8, 1000)
    xai = await generate_xai_explanation(farmer, farmer_user.name, crop, total_farmers_this_crop, total_demand_kg)
    assignment = CropAssignment(
        farmer_id=farmer.id,
        crop_id=crop.id,
        season=season,
        year=year,
        status=AssignmentStatus.pending,
        xai_explanation=f"{xai}\nAI planning reasons: {', '.join(top['reasons'])}.",
    )
    db.add(assignment)
    await check_oversupply(crop, total_supply_kg, total_demand_kg, db)
    recommendation = await save_recommendation(
        db,
        farmer,
        crop,
        "auto_assignment",
        top["confidence"],
        top["expected_profit"],
        top["reasons"],
    )
    await create_notification(
        db,
        farmer.user_id,
        f"AI auto-assigned {crop.crop_name} for {season} {year}. Please review the assignment.",
        "ai.auto_assignment.created",
    )
    await db.commit()
    await db.refresh(assignment)
    await manager.broadcast(
        f"notifications:{farmer.user_id}",
        {"event": "ai.auto_assignment.created", "assignment_id": str(assignment.id), "crop": crop.crop_name},
    )
    await manager.broadcast(
        "supply-demand",
        {"event": "supply_demand.updated", "crop_id": str(crop.id), "crop": crop.crop_name, "supply": total_supply_kg, "demand": total_demand_kg},
    )
    return {
        "assignment_id": assignment.id,
        "recommendation": recommendation_payload(recommendation, crop),
        "message": "AI assignment created and sent for farmer review",
    }


@router.post("/crop-rotation/{farmer_id}", response_model=RecommendationResponse)
async def crop_rotation(
    farmer_id: UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    farmer = await db.scalar(select(Farmer).where(Farmer.id == farmer_id))
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")
    recommendation = await generate_and_save_rotation_recommendation(db, farmer)
    if not recommendation:
        raise HTTPException(status_code=400, detail="No crops available for rotation")
    crop = await db.scalar(select(Crop).where(Crop.id == recommendation.crop_id))
    await db.commit()
    return recommendation_payload(recommendation, crop, include_next_crop=True)


@router.get("/recommendations", response_model=list[RecommendationResponse])
async def recommendation_history(
    farmer_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    query = select(CropRecommendation, Crop).join(Crop, CropRecommendation.crop_id == Crop.id)
    if farmer_id:
        query = query.where(CropRecommendation.farmer_id == farmer_id)
    rows = (await db.execute(query.order_by(desc(CropRecommendation.created_at)).limit(50))).all()
    return [recommendation_payload(rec, crop) for rec, crop in rows]


@router.get("/recommendations/me/latest", response_model=RecommendationResponse | None)
async def my_latest_recommendation(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role != UserRole.farmer:
        raise HTTPException(status_code=403, detail="Farmers only")
    row = (
        await db.execute(
            select(CropRecommendation, Crop)
            .join(Farmer, CropRecommendation.farmer_id == Farmer.id)
            .join(Crop, CropRecommendation.crop_id == Crop.id)
            .where(Farmer.user_id == current_user.id)
            .order_by(desc(CropRecommendation.created_at))
            .limit(1)
        )
    ).one_or_none()
    if not row:
        return None
    recommendation, crop = row
    return recommendation_payload(recommendation, crop)
