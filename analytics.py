from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from auth import require_admin
from db import get_db
from models import Crop, CropAssignment, DemandRequest, Farmer, Order, SupplyDemandLog, User

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/admin")
async def admin_analytics(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    supply_rows = (await db.execute(select(SupplyDemandLog, Crop).join(Crop).order_by(SupplyDemandLog.logged_at.desc()).limit(100))).all()
    crops = (await db.execute(select(Crop.crop_name, func.count(CropAssignment.id)).outerjoin(CropAssignment).group_by(Crop.id))).all()
    revenue = (await db.execute(select(func.date(Order.ordered_at), func.sum(Order.quantity_kg * Order.price_per_kg)).group_by(func.date(Order.ordered_at)).order_by(func.date(Order.ordered_at)))).all()
    growth = (await db.execute(select(func.date(User.created_at), func.count(Farmer.id)).join(Farmer).group_by(func.date(User.created_at)).order_by(func.date(User.created_at)))).all()
    high_demand = (
        await db.execute(
            select(Crop.crop_name, DemandRequest.status, func.sum(DemandRequest.quantity_kg))
            .join(Crop, DemandRequest.crop_id == Crop.id)
            .where(DemandRequest.status.in_(["open", "approved", "planned"]))
            .group_by(Crop.crop_name, DemandRequest.status)
            .order_by(func.sum(DemandRequest.quantity_kg).desc())
            .limit(10)
        )
    ).all()
    return {
        "supply_demand": [{"crop": crop.crop_name, "supply": log.total_supply_kg, "demand": log.total_demand_kg, "ratio": log.ratio} for log, crop in supply_rows],
        "crop_distribution": [{"name": name, "value": count} for name, count in crops],
        "revenue": [{"date": str(day), "revenue": float(value or 0)} for day, value in revenue],
        "farmer_growth": [{"date": str(day), "farmers": count} for day, count in growth],
        "high_demand": [{"crop_name": name, "status": status, "quantity_kg": float(quantity or 0)} for name, status, quantity in high_demand],
    }
