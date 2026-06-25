from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import date

from db import get_db
from models import (
    BabyCrop,
    CropAssignment,
    Farmer,
    Crop,
    MarketPrice,
    User,
    UserRole,
    GrowthStage,
    AssignmentStatus,
)
from auth import require_farmer
from notification_service import notify_role
from websocket import manager
from ai_planning import generate_and_save_rotation_recommendation

router = APIRouter(
    prefix="/baby-crops",
    tags=["Baby Crops"]
)

class BabyCropCreate(BaseModel):
    assignment_id: UUID
    sowing_date: date
    expected_harvest: Optional[date] = None
    quantity_kg: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None


class StageUpdate(BaseModel):
    growth_stage: str


class BabyCropResponse(BaseModel):
    id: UUID
    assignment_id: UUID
    growth_stage: str
    sowing_date: date
    expected_harvest: Optional[date]
    quantity_kg: Optional[float]
    notes: Optional[str]

    class Config:
        from_attributes = True

@router.post("/")
async def create_baby_crop(
    data: BabyCropCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    result = await db.execute(
        select(CropAssignment)
        .where(CropAssignment.id == data.assignment_id)
    )

    assignment = result.scalar_one_or_none()

    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="Assignment not found"
        )

    result = await db.execute(
        select(Farmer)
        .where(Farmer.user_id == current_user.id)
    )

    farmer = result.scalar_one_or_none()

    if not farmer:
        raise HTTPException(
            status_code=404,
            detail="Farmer profile not found"
        )

    if assignment.farmer_id != farmer.id:
        raise HTTPException(
            status_code=403,
            detail="Not your assignment"
        )

    if assignment.status not in {AssignmentStatus.accepted, AssignmentStatus.active}:
        raise HTTPException(
            status_code=400,
            detail="Assignment must be accepted before creating a baby crop"
        )

    duplicate_result = await db.execute(
        select(BabyCrop).where(BabyCrop.assignment_id == data.assignment_id)
    )
    if duplicate_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Baby crop already exists for this assignment")

    baby_crop = BabyCrop(
        assignment_id=data.assignment_id,
        sowing_date=data.sowing_date,
        expected_harvest=data.expected_harvest,
        quantity_kg=data.quantity_kg,
        notes=data.notes
    )

    db.add(baby_crop)
    crop_result = await db.execute(select(Crop).where(Crop.id == assignment.crop_id))
    crop = crop_result.scalar_one_or_none()
    await notify_role(
        db,
        UserRole.shop,
        f"{crop.crop_name if crop else 'A crop'} is now available in the marketplace.",
        "marketplace.updated",
    )
    await db.commit()
    await manager.broadcast("marketplace", {"event": "marketplace.updated", "baby_crop_id": str(baby_crop.id)})

    return {
        "message": "Baby crop created successfully"
    }

@router.get("/", response_model=List[BabyCropResponse])
async def get_my_baby_crops(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    result = await db.execute(
        select(Farmer)
        .where(Farmer.user_id == current_user.id)
    )

    farmer = result.scalar_one_or_none()

    if not farmer:
        raise HTTPException(
            status_code=404,
            detail="Farmer profile not found"
        )

    result = await db.execute(
        select(BabyCrop)
        .join(
            CropAssignment,
            BabyCrop.assignment_id == CropAssignment.id
        )
        .where(
            CropAssignment.farmer_id == farmer.id
        )
    )

    return result.scalars().all()

@router.get("/marketplace")
async def marketplace(
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(BabyCrop, CropAssignment, Farmer, User, Crop)
        .join(CropAssignment, BabyCrop.assignment_id == CropAssignment.id)
        .join(Farmer, CropAssignment.farmer_id == Farmer.id)
        .join(User, Farmer.user_id == User.id)
        .join(Crop, CropAssignment.crop_id == Crop.id)
        .where(
            BabyCrop.quantity_kg > 0
        )
    )

    marketplace_crops = []

    for baby_crop, assignment, farmer, user, crop in result.all():
        price_result = await db.execute(
            select(MarketPrice)
            .where(MarketPrice.crop_id == crop.id)
            .order_by(MarketPrice.recorded_at.desc())
            .limit(1)
        )
        latest_price = price_result.scalar_one_or_none()

        marketplace_crops.append({
            "id": baby_crop.id,
            "assignment_id": baby_crop.assignment_id,
            "crop_name": crop.crop_name,
            "growth_stage": baby_crop.growth_stage,
            "sowing_date": baby_crop.sowing_date,
            "expected_harvest": baby_crop.expected_harvest,
            "quantity_kg": baby_crop.quantity_kg,
            "notes": baby_crop.notes,
            "updated_at": baby_crop.updated_at,
            "availability_status": "available",
            "price_per_kg": latest_price.price_per_kg if latest_price else None,
            "farmer": {
                "name": user.name,
                "phone": user.phone,
                "email": user.email,
                "village": farmer.village,
                "district": farmer.district,
            },
        })

    return marketplace_crops

@router.put("/{baby_crop_id}/stage")
async def update_growth_stage(
    baby_crop_id: UUID,
    data: StageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    result = await db.execute(
        select(BabyCrop, CropAssignment, Farmer)
        .join(CropAssignment, BabyCrop.assignment_id == CropAssignment.id)
        .join(Farmer, CropAssignment.farmer_id == Farmer.id)
        .where(BabyCrop.id == baby_crop_id)
    )

    row = result.one_or_none()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Baby crop not found"
        )

    crop, assignment, farmer = row

    if farmer.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not your baby crop"
        )

    try:
        crop.growth_stage = GrowthStage(data.growth_stage)
    except ValueError as exc:
        allowed = ", ".join(stage.value for stage in GrowthStage)
        raise HTTPException(status_code=400, detail=f"Invalid growth stage. Allowed values: {allowed}") from exc

    await notify_role(
        db,
        UserRole.shop,
        "A marketplace crop growth stage was updated.",
        "marketplace.updated",
    )
    rotation_recommendation = None
    if crop.growth_stage == GrowthStage.harvest:
        rotation_recommendation = await generate_and_save_rotation_recommendation(db, farmer)
    await db.commit()
    await manager.broadcast("marketplace", {"event": "marketplace.updated", "baby_crop_id": str(crop.id), "growth_stage": crop.growth_stage.value})
    if rotation_recommendation:
        await manager.broadcast(
            f"notifications:{farmer.user_id}",
            {
                "event": "ai.rotation.created",
                "recommendation_id": str(rotation_recommendation.id),
                "farmer_id": str(farmer.id),
            },
        )

    return {
        "message": "Growth stage updated"
    }
@router.get("/{baby_crop_id}")
async def get_baby_crop(
    baby_crop_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_farmer)
):
    result = await db.execute(
        select(BabyCrop, CropAssignment, Farmer)
        .join(CropAssignment, BabyCrop.assignment_id == CropAssignment.id)
        .join(Farmer, CropAssignment.farmer_id == Farmer.id)
        .where(BabyCrop.id == baby_crop_id)
    )

    row = result.one_or_none()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Baby crop not found"
        )

    crop, assignment, farmer = row

    if farmer.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Not your baby crop"
        )

    return crop
