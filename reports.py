"""Downloadable admin reports in CSV, Excel, or PDF formats."""
from io import BytesIO, StringIO
import csv
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from auth import require_admin
from db import get_db
from models import Crop, Farmer, Order, Shop, User

router = APIRouter(prefix="/reports", tags=["Reports"])

def _response(title: str, rows: list[dict], format: Literal["csv", "xlsx", "pdf"]):
    if format == "csv":
        stream = StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ["message"])
        writer.writeheader(); writer.writerows(rows or [{"message": "No records"}])
        return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{title}.csv"'})
    if format == "xlsx":
        try:
            import pandas as pd
            stream = BytesIO(); pd.DataFrame(rows).to_excel(stream, index=False, engine="openpyxl"); stream.seek(0)
            return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{title}.xlsx"'})
        except ImportError as error:
            raise HTTPException(503, "Excel reporting requires openpyxl") from error
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
        from reportlab.lib.styles import getSampleStyleSheet
        stream = BytesIO(); doc = SimpleDocTemplate(stream, pagesize=A4); styles = getSampleStyleSheet()
        table = [list(rows[0].keys())] + [list(map(str, row.values())) for row in rows] if rows else [["Message"], ["No records"]]
        doc.build([Paragraph(f"Cropverse {title.title()} Report", styles["Title"]), Spacer(1, 12), Table(table, repeatRows=1)])
        stream.seek(0)
        return StreamingResponse(stream, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{title}.pdf"'})
    except ImportError as error:
        raise HTTPException(503, "PDF reporting requires reportlab") from error

@router.get("/farmers")
async def farmer_report(format: Literal["csv", "xlsx", "pdf"] = "csv", db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    records = (await db.execute(select(Farmer, User).join(User))).all()
    rows = [{"name": user.name, "email": user.email, "district": farmer.district, "village": farmer.village, "soil_type": farmer.soil_type, "land_acres": farmer.land_acres} for farmer, user in records]
    return _response("farmers", rows, format)

@router.get("/orders")
async def orders_report(format: Literal["csv", "xlsx", "pdf"] = "csv", db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    records = (await db.execute(select(Order, Shop).join(Shop))).all()
    rows = [{"order_id": str(order.id), "shop": shop.shop_name, "quantity_kg": order.quantity_kg, "price_per_kg": order.price_per_kg, "total": order.quantity_kg * order.price_per_kg, "status": order.status.value, "ordered_at": order.ordered_at.isoformat()} for order, shop in records]
    return _response("orders", rows, format)

@router.get("/crops")
async def crops_report(format: Literal["csv", "xlsx", "pdf"] = "csv", db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    crops = (await db.execute(select(Crop))).scalars().all()
    rows = [{"crop": crop.crop_name, "season": crop.season, "soil_suitability": crop.soil_suitability, "average_yield_per_acre": crop.avg_yield_per_acre, "min_price": crop.min_price, "max_price": crop.max_price} for crop in crops]
    return _response("crops", rows, format)
