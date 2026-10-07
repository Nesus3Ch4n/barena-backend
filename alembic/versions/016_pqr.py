"""tabla pqr para peticiones, quejas, reclamos, sugerencias y felicitaciones por torneo

Revision ID: 016_pqr
Revises: 015_oficiales_rol
Create Date: 2026-10-07
"""
from alembic import op

revision = "016_pqr"
down_revision = "015_oficiales_rol"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS pqr (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    torneo_id UUID NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    tipo VARCHAR(20) NOT NULL DEFAULT 'peticion',
    asunto VARCHAR(120) NOT NULL,
    mensaje TEXT NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'abierta',
    respuesta TEXT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_pqr_torneo ON pqr (torneo_id);
    """)


def downgrade() -> None:
    op.execute("""
DROP INDEX IF EXISTS ix_pqr_torneo;
DROP TABLE IF EXISTS pqr;
    """)
