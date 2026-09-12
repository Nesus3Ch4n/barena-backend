"""add diferencia_dos_puntos to categorias

Revision ID: 006_categoria_diferencia
Revises: 005_torneo_datetime
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa

revision = "006_categoria_diferencia"
down_revision = "005_torneo_datetime"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
        ALTER TABLE categorias ADD COLUMN IF NOT EXISTS diferencia_dos_puntos BOOLEAN DEFAULT TRUE;
        UPDATE categorias SET diferencia_dos_puntos=TRUE WHERE diferencia_dos_puntos IS NULL;
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE categorias DROP COLUMN IF EXISTS diferencia_dos_puntos;
    """)
