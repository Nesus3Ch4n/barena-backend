"""columna rol en torneo_jueces para los 8 oficiales del torneo

Revision ID: 015_oficiales_rol
Revises: 014_reglas
Create Date: 2026-09-28
"""
from alembic import op

revision = "015_oficiales_rol"
down_revision = "014_reglas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE torneo_jueces ADD COLUMN IF NOT EXISTS rol VARCHAR(24);
CREATE UNIQUE INDEX IF NOT EXISTS uq_torneo_jueces_rol ON torneo_jueces (torneo_id, rol) WHERE rol IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("""
-- downgrade
DROP INDEX IF EXISTS uq_torneo_jueces_rol;
ALTER TABLE torneo_jueces DROP COLUMN IF EXISTS rol;
    """)
