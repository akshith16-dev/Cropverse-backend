import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Boolean,
    Integer, ForeignKey, Enum, Text, DateTime, Date
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
from db import Base


# ─── Enums ────────────────────────────────

class UserRole(str, enum.Enum):
    admin  = "admin"
    farmer = "farmer"
    shop   = "shop"

class GrowthStage(str, enum.Enum):
    sowing      = "sowing"
    germination = "germination"
    vegetative  = "vegetative"
    flowering   = "flowering"
    fruiting    = "fruiting"
    harvest     = "harvest"

class OrderStatus(str, enum.Enum):
    pending    = "pending"
    confirmed  = "confirmed"
    dispatched = "dispatched"
    delivered  = "delivered"
    rejected   = "rejected"
    cancelled  = "cancelled"

class OrderType(str, enum.Enum):
    spot     = "spot"
    contract = "contract"

class AlertLevel(str, enum.Enum):
    normal   = "normal"
    warning  = "warning"
    critical = "critical"

class AssignmentStatus(str, enum.Enum):
    pending  = "pending"
    accepted = "accepted"
    rejected = "rejected"
    active   = "active"
    complete = "complete"


# ─── Users ────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name          = Column(String(150), nullable=False)
    email         = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role          = Column(Enum(UserRole), nullable=False)
    phone         = Column(String(20), nullable=True)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    farmer        = relationship("Farmer", back_populates="user", uselist=False)
    shop          = relationship("Shop", back_populates="user", uselist=False)
    notifications = relationship("Notification", back_populates="user")


# ─── Farmers ──────────────────────────────

class Farmer(Base):
    __tablename__ = "farmers"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    village    = Column(String(100), nullable=False)
    district   = Column(String(100), nullable=False)
    soil_type  = Column(String(50), nullable=False)
    land_acres = Column(Float, nullable=False)
    micro_zone = Column(String(50), nullable=True)
    latitude   = Column(Float, nullable=True)
    longitude  = Column(Float, nullable=True)

    user        = relationship("User", back_populates="farmer")
    assignments = relationship("CropAssignment", back_populates="farmer")
    rotations   = relationship("CropRotation", back_populates="farmer")


# ─── Shops ────────────────────────────────

class Shop(Base):
    __tablename__ = "shops"

    id        = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id   = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    shop_name = Column(String(150), nullable=False)
    location  = Column(String(200), nullable=False)
    contact   = Column(String(20), nullable=True)

    user    = relationship("User", back_populates="shop")
    demands = relationship("DemandRequest", back_populates="shop")
    orders  = relationship("Order", back_populates="shop")


# ─── Crops ────────────────────────────────

class Crop(Base):
    __tablename__ = "crops"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crop_name          = Column(String(100), nullable=False, unique=True)
    season             = Column(String(50), nullable=False)
    soil_suitability   = Column(String(200), nullable=False)
    avg_yield_per_acre = Column(Float, nullable=False)
    min_price          = Column(Float, nullable=False)
    max_price          = Column(Float, nullable=False)
    cultivation_cost   = Column(Float, nullable=False)

    assignments = relationship("CropAssignment", back_populates="crop")
    rotations   = relationship("CropRotation", back_populates="crop")
    prices      = relationship("MarketPrice", back_populates="crop")
    demands     = relationship("DemandRequest", back_populates="crop")
    supply_logs = relationship("SupplyDemandLog", back_populates="crop")


# ─── Crop Assignments ─────────────────────

class CropAssignment(Base):
    __tablename__ = "crop_assignments"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farmer_id       = Column(UUID(as_uuid=True), ForeignKey("farmers.id"), nullable=False)
    crop_id         = Column(UUID(as_uuid=True), ForeignKey("crops.id"), nullable=False)
    season          = Column(String(20), nullable=False)
    year            = Column(Integer, nullable=False)
    status          = Column(Enum(AssignmentStatus), default=AssignmentStatus.pending)
    xai_explanation = Column(Text, nullable=True)
    assigned_at     = Column(DateTime, default=datetime.utcnow)

    farmer     = relationship("Farmer", back_populates="assignments")
    crop       = relationship("Crop", back_populates="assignments")
    baby_crops = relationship("BabyCrop", back_populates="assignment")


# ─── Crop Rotation ────────────────────────

class CropRotation(Base):
    __tablename__ = "crop_rotations"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farmer_id     = Column(UUID(as_uuid=True), ForeignKey("farmers.id"), nullable=False)
    crop_id       = Column(UUID(as_uuid=True), ForeignKey("crops.id"), nullable=False)
    season_number = Column(Integer, nullable=False)
    year          = Column(Integer, nullable=False)

    farmer = relationship("Farmer", back_populates="rotations")
    crop   = relationship("Crop", back_populates="rotations")


# ─── Baby Crops ───────────────────────────

class BabyCrop(Base):
    __tablename__ = "baby_crops"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id    = Column(UUID(as_uuid=True), ForeignKey("crop_assignments.id"), nullable=False)
    growth_stage     = Column(Enum(GrowthStage), default=GrowthStage.sowing)
    sowing_date      = Column(Date, nullable=False)
    expected_harvest = Column(Date, nullable=True)
    quantity_kg      = Column(Float, nullable=True)
    notes            = Column(Text, nullable=True)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignment = relationship("CropAssignment", back_populates="baby_crops")
    orders     = relationship("Order", back_populates="baby_crop")


# ─── Market Prices ────────────────────────

class MarketPrice(Base):
    __tablename__ = "market_prices"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crop_id      = Column(UUID(as_uuid=True), ForeignKey("crops.id"), nullable=False)
    price_per_kg = Column(Float, nullable=False)
    fair_price   = Column(Float, nullable=False)
    market_name  = Column(String(100), nullable=False)
    recorded_at  = Column(DateTime, default=datetime.utcnow)

    crop = relationship("Crop", back_populates="prices")


# ─── Demand Requests ──────────────────────

class DemandRequest(Base):
    __tablename__ = "demand_requests"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id     = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    crop_id     = Column(UUID(as_uuid=True), ForeignKey("crops.id"), nullable=False)
    quantity_kg = Column(Float, nullable=False)
    required_by = Column(Date, nullable=False)
    status      = Column(String(30), default="open")
    created_at  = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="demands")
    crop = relationship("Crop", back_populates="demands")


# ─── Orders ───────────────────────────────

class Order(Base):
    __tablename__ = "orders"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id      = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    baby_crop_id = Column(UUID(as_uuid=True), ForeignKey("baby_crops.id"), nullable=False)
    quantity_kg  = Column(Float, nullable=False)
    price_per_kg = Column(Float, nullable=False)
    order_type   = Column(Enum(OrderType), default=OrderType.spot)
    status       = Column(Enum(OrderStatus), default=OrderStatus.pending)
    ordered_at   = Column(DateTime, default=datetime.utcnow)

    shop      = relationship("Shop", back_populates="orders")
    baby_crop = relationship("BabyCrop", back_populates="orders")


# ─── Supply Demand Log ────────────────────

class SupplyDemandLog(Base):
    __tablename__ = "supply_demand_log"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crop_id         = Column(UUID(as_uuid=True), ForeignKey("crops.id"), nullable=False)
    total_supply_kg = Column(Float, nullable=False)
    total_demand_kg = Column(Float, nullable=False)
    ratio           = Column(Float, nullable=False)
    alert_level     = Column(Enum(AlertLevel), default=AlertLevel.normal)
    logged_at       = Column(DateTime, default=datetime.utcnow)

    crop = relationship("Crop", back_populates="supply_logs")


# ─── Notifications ────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    type    = Column(String(50), nullable=False)
    is_read = Column(Boolean, default=False)
    sent_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")
