from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID
from db import get_db
from config import settings
from models import User, Farmer, Shop, UserRole

router = APIRouter(prefix="/auth", tags=["Auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload.update({"exp": expire})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# ─── Schemas ──────────────────────────────

class RegisterFarmer(BaseModel):
    name:       str
    email:      EmailStr
    password:   str
    phone:      Optional[str] = None
    village:    str
    district:   str
    soil_type:  str
    land_acres: float

class RegisterShop(BaseModel):
    name:      str
    email:     EmailStr
    password:  str
    phone:     Optional[str] = None
    shop_name: str
    location:  str

class RegisterAdmin(BaseModel):
    name:     str
    email:    EmailStr
    password: str
    phone:    Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str
    role:         str
    user_name:    str


# ─── Register ─────────────────────────────

@router.post("/register/farmer", response_model=TokenResponse, status_code=201)
async def register_farmer(data: RegisterFarmer, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        name=data.name, email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole.farmer, phone=data.phone
    )
    db.add(user)
    await db.flush()

    farmer = Farmer(
        user_id=user.id,
        village=data.village,
        district=data.district,
        soil_type=data.soil_type,
        land_acres=data.land_acres
    )
    db.add(farmer)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(access_token=token, token_type="bearer",
                         role=user.role, user_name=user.name)


@router.post("/register/shop", response_model=TokenResponse, status_code=201)
async def register_shop(data: RegisterShop, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        name=data.name, email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole.shop, phone=data.phone
    )
    db.add(user)
    await db.flush()

    shop = Shop(
        user_id=user.id,
        shop_name=data.shop_name,
        location=data.location,
        contact=data.phone
    )
    db.add(shop)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(access_token=token, token_type="bearer",
                         role=user.role, user_name=user.name)


@router.post("/register/admin", response_model=TokenResponse, status_code=201)
async def register_admin(data: RegisterAdmin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        name=data.name, email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole.admin, phone=data.phone
    )
    db.add(user)
    await db.commit()

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(access_token=token, token_type="bearer",
                         role=user.role, user_name=user.name)


# ─── Login ────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(),
                db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form.username))
    user: User = result.scalar_one_or_none()

    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(access_token=token, token_type="bearer",
                         role=user.role, user_name=user.name)


# ─── Get Current User ─────────────────────

async def get_current_user(token: str = Depends(oauth2_scheme),
                           db: AsyncSession = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY,
                             algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


# ─── Role Guards ──────────────────────────

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

async def require_farmer(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.farmer:
        raise HTTPException(status_code=403, detail="Farmer access required")
    return current_user

async def require_shop(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.shop:
        raise HTTPException(status_code=403, detail="Shop access required")
    return current_user