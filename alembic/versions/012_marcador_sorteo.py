"""columnas de sorteo/saque/inicio/fin en partidos (marcador virtual)

Revision ID: 012_marcador_sorteo
Revises: 011_clasificados
Create Date: 2026-09-22
"""
from alembic import op

revision = "012_marcador_sorteo"
down_revision = "011_clasificados"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE partidos ADD COLUMN IF NOT EXISTS sorteo_ganador_id UUID REFERENCES equipos(id);
ALTER TABLE partidos ADD COLUMN IF NOT EXISTS saque_equipo_id UUID REFERENCES equipos(id);
ALTER TABLE partidos ADD COLUMN IF NOT EXISTS saque_atleta_id VARCHAR(36);
ALTER TABLE partidos ADD COLUMN IF NOT EXISTS iniciado_en TIMESTAMPTZ;
ALTER TABLE partidos ADD COLUMN IF NOT EXISTS iniciado_por UUID REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE partidos ADD COLUMN IF NOT EXISTS finalizado_en TIMESTAMPTZ;
    """)


def downgrade() -> None:
    op.execute("""
-- downgrade
ALTER TABLE partidos DROP COLUMN IF EXISTS sorteo_ganador_id;
ALTER TABLE partidos DROP COLUMN IF EXISTS saque_equipo_id;
ALTER TABLE partidos DROP COLUMN IF EXISTS saque_atleta_id;
ALTER TABLE partidos DROP COLUMN IF EXISTS iniciado_en;
ALTER TABLE partidos DROP COLUMN IF EXISTS iniciado_por;
ALTER TABLE partidos DROP COLUMN IF EXISTS finalizado_en;
    """)
