from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from db import get_db
from gemini_client import generate_gemini_text
from models import (
    CropAssignment, Farmer, Crop, User,
    AssignmentStatus, SupplyDemandLog, AlertLevel, UserRole
)
from auth import require_admin, require_farmer, get_current_user
from notification_service import create_notification, notify_role
from websocket import manager

router = APIRouter(prefix="/assignments", tags=["Assignments"])

# ─── Schemas ──────────────────────────────

class AssignmentCreate(BaseModel):
    farmer_id: UUID
    crop_id:   UUID
    season:    str
    year:      int

class AssignmentResponse(BaseModel):
    id:              UUID
    farmer_id:       UUID
    crop_id:         UUID
    farmer_name:     str
    crop_name:       str
    season:          str
    year:            int
    status:          str
    xai_explanation: Optional[str] = None
    assigned_at:     datetime

    class Config:
        from_attributes = True

class StatusUpdate(BaseModel):
    status: str   # accepted / rejected


# ─── XAI — Generate explanation via Gemini ─

async def generate_xai_explanation(
    farmer: Farmer,
    farmer_name: str,
    crop: Crop,
    total_farmers_this_crop: int,
    total_demand_kg: float,
) -> str:
    fallback = (
        f"{crop.crop_name} was assigned to {farmer_name} based on "
        f"soil compatibility ({farmer.soil_type}) and current market demand."
    )
    prompt = f"""
You are an agricultural advisor AI for Cropverse platform.
Explain in 2-3 simple sentences why this crop was assigned to this farmer.
Be specific, friendly and easy to understand.

Farmer details:
- Name: {farmer_name}
- Village: {farmer.village}
- District: {farmer.district}
- Soil type: {farmer.soil_type}
- Land: {farmer.land_acres} acres

Crop details:
- Crop: {crop.crop_name}
- Season: {crop.season}
- Suitable soils: {crop.soil_suitability}
- Average yield: {crop.avg_yield_per_acre} kg/acre
- Fair price: ₹{round(crop.cultivation_cost * 1.2, 2)}/kg
- Farmers already growing this crop this season: {total_farmers_this_crop}
- Total market demand: {total_demand_kg} kg

Give a short, clear explanation starting with "This crop was assigned because..."
"""
    return await generate_gemini_text(prompt, "gemini-1.5-flash") or fallback


# ─── Check oversupply ─────────────────────

async def check_oversupply(
    crop: Crop,
    total_supply_kg: float,
    total_demand_kg: float,
    db: AsyncSession
):
    ratio = total_supply_kg / total_demand_kg if total_demand_kg > 0 else 999

    if ratio >= 1.5:
        alert = AlertLevel.critical
    elif ratio >= 1.2:
        alert = AlertLevel.warning
    else:
        alert = AlertLevel.normal

    log = SupplyDemandLog(
        crop_id=crop.id,
        total_supply_kg=total_supply_kg,
        total_demand_kg=total_demand_kg,
        ratio=round(ratio, 2),
        alert_level=alert,
    )
    db.add(log)


# ─── Assign crop to farmer (admin only) ───

@router.post("/", response_model=AssignmentResponse, status_code=201)
async def assign_crop(
    data: AssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin)
):
    # get farmer
    result = await db.execute(
        select(Farmer, User)
        .join(User, Farmer.user_id == User.id)
        .where(Farmer.id == data.farmer_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Farmer not found")
    farmer, farmer_user = row

    # get crop
    result = await db.execute(select(Crop).where(Crop.id == data.crop_id))
    crop = result.scalar_one_or_none()
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found")

    # check duplicate assignment
    result = await db.execute(
        select(CropAssignment).where(
            CropAssignment.farmer_id == data.farmer_id,
            CropAssignment.season == data.season,
            CropAssignment.year == data.year,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Farmer already has a crop assigned for this season"
        )

    # count how many farmers are growing this crop this season
    count_result = await db.execute(
        select(func.count(CropAssignment.id)).where(
            CropAssignment.crop_id == data.crop_id,
            CropAssignment.season == data.season,
            CropAssignment.year == data.year,
        )
    )
    total_farmers_this_crop = count_result.scalar() or 0

    # estimate total supply
    total_supply_kg = (total_farmers_this_crop + 1) * farmer.land_acres * crop.avg_yield_per_acre

    # estimate total demand (simple: 1000kg per shop demand as placeholder)
    total_demand_kg = max(total_supply_kg * 0.8, 1000)

    # generate XAI explanation
    xai = await generate_xai_explanation(
        farmer, farmer_user.name, crop,
        total_farmers_this_crop, total_demand_kg
    )

    # create assignment
    assignment = CropAssignment(
        farmer_id=data.farmer_id,
        crop_id=data.crop_id,
        season=data.season,
        year=data.year,
        status=AssignmentStatus.pending,
        xai_explanation=xai,
    )
    db.add(assignment)

    # log supply vs demand
    await check_oversupply(crop, total_supply_kg, total_demand_kg, db)
    await create_notification(
        db,
        farmer.user_id,
        f"{crop.crop_name} was assigned to you for {data.season} {data.year}.",
        "assignment.created",
    )

    await db.commit()
    await db.refresh(assignment)
    await manager.broadcast("supply-demand", {"event": "supply_demand.updated", "crop_id": str(crop.id), "crop": crop.crop_name, "supply": total_supply_kg, "demand": total_demand_kg})
    await manager.broadcast(f"notifications:{farmer.user_id}", {"event": "assignment.created", "assignment_id": str(assignment.id), "crop": crop.crop_name})

    return AssignmentResponse(
        id=assignment.id,
        farmer_id=assignment.farmer_id,
        crop_id=assignment.crop_id,
        farmer_name=farmer_user.name,
        crop_name=crop.crop_name,
        season=assignment.season,
        year=assignment.year,
        status=assignment.status,
        xai_explanation=assignment.xai_explanation,
        assigned_at=assignment.assigned_at,
    )


# ─── Get all assignments (admin only) ─────

@router.get("/", response_model=List[AssignmentResponse])
async def get_all_assignments(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin)
):
    result = await db.execute(
        select(CropAssignment, Farmer, User, Crop)
        .join(Farmer, CropAssignment.farmer_id == Farmer.id)
        .join(User, Farmer.user_id == User.id)
        .join(Crop, CropAssignment.crop_id == Crop.id)
    )
    rows = result.all()

    return [
        AssignmentResponse(
            id=a.id,
            farmer_id=a.farmer_id,
            crop_id=a.crop_id,
            farmer_name=u.name,
            crop_name=c.crop_name,
            season=a.season,
            year=a.year,
            status=a.status,
            xai_explanation=a.xai_explanation,
            assigned_at=a.assigned_at,
        )
        for a, f, u, c in rows
    ]


# ─── Get my assignments (farmer only) ─────

@router.get("/me", response_model=List[AssignmentResponse])
async def get_my_assignments(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_farmer)
):
    # get farmer profile
    result = await db.execute(
        select(Farmer).where(Farmer.user_id == current_user.id)
    )
    farmer = result.scalar_one_or_none()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer profile not found")

    result = await db.execute(
        select(CropAssignment, Crop)
        .join(Crop, CropAssignment.crop_id == Crop.id)
        .where(CropAssignment.farmer_id == farmer.id)
    )
    rows = result.all()

    return [
        AssignmentResponse(
            id=a.id,
            farmer_id=a.farmer_id,
            crop_id=a.crop_id,
            farmer_name=current_user.name,
            crop_name=c.crop_name,
            season=a.season,
            year=a.year,
            status=a.status,
            xai_explanation=a.xai_explanation,
            assigned_at=a.assigned_at,
        )
        for a, c in rows
    ]


# ─── Farmer accepts or rejects assignment ─

@router.put("/{assignment_id}/status")
async def update_assignment_status(
    assignment_id: UUID,
    data: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_farmer)
):
    if data.status not in ["accepted", "rejected"]:
        raise HTTPException(status_code=400, detail="Status must be accepted or rejected")

    result = await db.execute(
        select(CropAssignment, Farmer)
        .join(Farmer, CropAssignment.farmer_id == Farmer.id)
        .where(CropAssignment.id == assignment_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")

    assignment, farmer = row

    # make sure this farmer owns this assignment
    if farmer.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your assignment")

    crop_result = await db.execute(select(Crop).where(Crop.id == assignment.crop_id))
    crop = crop_result.scalar_one_or_none()
    assignment.status = data.status
    await notify_role(
        db,
        UserRole.admin,
        f"{current_user.name} {data.status} the {crop.crop_name if crop else 'crop'} assignment.",
        "assignment.status",
    )
    await db.commit()

    return {"message": f"Assignment {data.status} successfully"}


# ─── Get oversupply alerts (admin only) ───

@router.get("/alerts/oversupply")
async def get_oversupply_alerts(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin)
):
    result = await db.execute(
        select(SupplyDemandLog, Crop)
        .join(Crop, SupplyDemandLog.crop_id == Crop.id)
        .where(SupplyDemandLog.alert_level != AlertLevel.normal)
        .order_by(SupplyDemandLog.logged_at.desc())
    )
    rows = result.all()

    alerts = []
    for log, crop in rows:
        alerts.append({
            "crop_name":       crop.crop_name,
            "total_supply_kg": log.total_supply_kg,
            "total_demand_kg": log.total_demand_kg,
            "ratio":           log.ratio,
            "alert_level":     log.alert_level,
            "logged_at":       log.logged_at,
        })
    return alerts
