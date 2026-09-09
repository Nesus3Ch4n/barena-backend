import os
import sys
from logging.config import fileConfig
from sqlalchemy import pool, create_engine
from alembic import context

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.shared.database import Base  # noqa: F401  # import all models
# Ensure all models are imported so Base.metadata includes them
import app.auth.models  # noqa: F401
import app.torneos.models  # noqa: F401
import app.equipos.models  # noqa: F401
import app.atletas.models  # noqa: F401
import app.partidos.models  # noqa: F401
import app.estadisticas.models  # noqa: F401
import app.rankings.models  # noqa: F401
import app.reportes.models  # noqa: F401
import app.config.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def get_url():
    # Prefer SYNC url for alembic (psycopg2)
    url = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL", "")
    # alembic needs sync driver, replace async drivers -> plain postgresql (psycopg2)
    if url.startswith("postgresql+asyncpg"):
        url = url.replace("postgresql+asyncpg", "postgresql")
    if url.startswith("postgresql+psycopg"):
        url = url.replace("postgresql+psycopg", "postgresql")
    if url:
        return url
    return config.get_main_option("sqlalchemy.url")

def run_migrations_offline() -> None:
    url = get_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = create_engine(get_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
