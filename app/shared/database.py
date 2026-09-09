"""
ServeTrack — DB async (Supabase Postgres via asyncpg)
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql+psycopg://postgres:postgres@localhost:5432/servetrack"

# Evitar crash si Vercel deja DATABASE_URL vacío ("")
if not DATABASE_URL or DATABASE_URL.strip() == "":
    DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/servetrack"

# pgbouncer (Supabase pooler) no soporta prepared statements
# psycopg3 (psycopg) no usa prepared statements -> compatible con pgbouncer transaction mode
from sqlalchemy.pool import NullPool

# Swap asyncpg -> psycopg if DATABASE_URL still uses asyncpg prefix
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    poolclass=NullPool,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

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
