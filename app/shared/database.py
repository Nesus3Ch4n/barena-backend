"""
ServeTrack — DB async (Supabase Postgres via asyncpg)
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql+asyncpg://postgres:postgres@localhost:5432/servetrack"

# Evitar crash si Vercel deja DATABASE_URL vacío ("")
if not DATABASE_URL or DATABASE_URL.strip() == "":
    DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/servetrack"

# pgbouncer (Supabase pooler) no soporta prepared statements -> desactivar cache
# asyncpg + pgbouncer transaction mode: statement_cache_size=0 es obligatorio
# Se fuerza via URL + connect_args + NullPool para evitar cache en Vercel
from sqlalchemy.pool import NullPool
if "statement_cache_size" not in DATABASE_URL:
    sep = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL = f"{DATABASE_URL}{sep}statement_cache_size=0"
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    poolclass=NullPool,
    connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
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
