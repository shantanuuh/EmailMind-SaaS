# backend/app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import redis
from .config import settings

# PostgreSQL Database
engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.DEBUG
)

SessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

# Redis Connection
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

# Database Dependency
async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# Redis Dependency
def get_redis():
    return redis_client
