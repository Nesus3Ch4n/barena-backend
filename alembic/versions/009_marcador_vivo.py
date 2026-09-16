"""marcador en vivo del partido (bitácora de eventos del juez)

Tabla partido_eventos: cada acción del juez durante el partido en juego se
registra como evento (punto, set ganado, tiempo muerto/receso/médico, tarjeta
amarilla/roja, saque, orden de saque, cambio de lado, acción individual por
atleta). El estado del marcador se deriva del log; 'revocado' permite deshacer.

Revision ID: 009_marcador_vivo
Revises: 008_bracket_llaves
Create Date: 2026-09-15
"""
from alembic import op

revision = "009_marcador_vivo"
down_revision = "008_bracket_llaves"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS partido_eventos (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            partido_id UUID NOT NULL REFERENCES partidos(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL,
            tipo VARCHAR(24) NOT NULL,
            lado VARCHAR(10),
            atleta_id VARCHAR(36),
            razon VARCHAR(24),
            numero INTEGER,
            extra JSONB,
            revocado BOOLEAN NOT NULL DEFAULT FALSE,
            creado_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_partido_eventos_partido_seq
            ON partido_eventos (partido_id, seq);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS partido_eventos;
    """)