"""tabla clasificacion_congelada + criterio_emparejamiento

Revision ID: 013_snapshot
Revises: 012_marcador_sorteo
Create Date: 2026-09-22
"""
from alembic import op

revision = "013_snapshot"
down_revision = "012_marcador_sorteo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE categorias ADD COLUMN IF NOT EXISTS clasificados INTEGER;
ALTER TABLE categorias ADD COLUMN IF NOT EXISTS criterio_emparejamiento TEXT DEFAULT 'directo';

CREATE TABLE IF NOT EXISTS clasificacion_congelada (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    categoria_id UUID NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
    creada_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    criterio TEXT NOT NULL DEFAULT 'PG>CS>CP>JL',
    clasificados INT NULL,
    emparejamiento TEXT NOT NULL DEFAULT 'directo',
    filas JSONB NOT NULL DEFAULT '[]'::jsonb,
    bracket JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_clasif_congelada_cat ON clasificacion_congelada (categoria_id, creada_en DESC);
    """)


def downgrade() -> None:
    op.execute("""
-- downgrade
DROP TABLE IF EXISTS clasificacion_congelada;
ALTER TABLE categorias DROP COLUMN IF EXISTS criterio_emparejamiento;
    """)
