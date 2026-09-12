"""torneo fecha con hora

Revision ID: 005_torneo_datetime
Revises: 004_sets_criterios
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa

revision = "005_torneo_datetime"
down_revision = "004_sets_criterios"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
        ALTER TABLE torneos ALTER COLUMN fecha_inicio TYPE TIMESTAMPTZ USING fecha_inicio::timestamptz;
        ALTER TABLE torneos ALTER COLUMN fecha_fin TYPE TIMESTAMPTZ USING fecha_fin::timestamptz;
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE torneos ALTER COLUMN fecha_inicio TYPE DATE USING fecha_inicio::date;
        ALTER TABLE torneos ALTER COLUMN fecha_fin TYPE DATE USING fecha_fin::date;
    """)
