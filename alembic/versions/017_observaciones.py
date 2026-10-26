"""observaciones del juez en partidos

Revision ID: 017_observaciones
Revises: 016_pqr
Create Date: 2026-10-25
"""
from alembic import op

revision = "017_observaciones"
down_revision = "016_pqr"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE partidos ADD COLUMN IF NOT EXISTS observaciones TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE partidos DROP COLUMN IF EXISTS observaciones")
