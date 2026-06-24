from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import settings

database_url = settings.DATABASE_URL
# Render commonly provides postgres:// while SQLAlchemy async requires asyncpg.
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine_options = {"echo": settings.DEBUG, "pool_pre_ping": True}
if database_url.startswith("sqlite"):
    # SQLite needs this option; asyncpg/PostgreSQL must not receive it.
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(database_url, **engine_options)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
