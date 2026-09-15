"""add bracket enlaces entre rondas

Revision ID: 008_bracket_enlaces
Revises: 007_juego_limpio
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa

revision = "008_bracket_enlaces"
down_revision = "007_juego_limpio"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
        ALTER TABLE partidos ADD COLUMN IF NOT EXISTS orden_en_round INTEGER;
        ALTER TABLE partidos ADD COLUMN IF NOT EXISTS partido_siguiente_id UUID REFERENCES partidos(id) ON DELETE SET NULL;
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE partidos DROP COLUMN IF EXISTS partido_siguiente_id;
        ALTER TABLE partidos DROP COLUMN IF EXISTS orden_en_round;
    """)