"""columna reglas_partido JSON en categorias

Revision ID: 014_reglas
Revises: 013_snapshot
Create Date: 2026-09-22
"""
from alembic import op

revision = "014_reglas"
down_revision = "013_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE categorias ADD COLUMN IF NOT EXISTS reglas_partido JSONB DEFAULT '{}'::jsonb;
    """)


def downgrade() -> None:
    op.execute("""
-- downgrade
ALTER TABLE categorias DROP COLUMN IF EXISTS reglas_partido;
    """)
