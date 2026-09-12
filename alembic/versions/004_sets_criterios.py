"""sets 1-3 + punto de oro + criterios 16 + 3/2/1

Revision ID: 004_sets_criterios
Revises: 003_categoria_brackets
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa

revision = "004_sets_criterios"
down_revision = "003_categoria_brackets"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
        -- sets 1,2,3 (antes 1,3,5) y criterio mas largo
        ALTER TABLE categorias DROP CONSTRAINT IF EXISTS categorias_sets_x_partido_check;
        ALTER TABLE categorias ADD CONSTRAINT categorias_sets_x_partido_check CHECK (sets_x_partido IN (1,2,3));
        ALTER TABLE categorias ALTER COLUMN criterio_clasif TYPE VARCHAR(200);
        UPDATE categorias SET criterio_clasif='PG>SF>PF>DP' WHERE criterio_clasif='V>S>P>DP';

        -- rankings: agregar pe y pts para 3/2/1
        ALTER TABLE rankings_grupo ADD COLUMN IF NOT EXISTS pe INTEGER DEFAULT 0;
        ALTER TABLE rankings_grupo ADD COLUMN IF NOT EXISTS pts INTEGER DEFAULT 0;
        ALTER TABLE rankings_general ADD COLUMN IF NOT EXISTS pe INTEGER DEFAULT 0;
        ALTER TABLE rankings_general ADD COLUMN IF NOT EXISTS pts INTEGER DEFAULT 0;
        -- cocientes como columnas generadas o calculadas en trigger, por ahora solo pts
        UPDATE rankings_grupo SET pe=0, pts=pg*3 + (pj-pg)*1 WHERE pe IS NULL OR pts IS NULL;
        UPDATE rankings_general SET pe=0, pts=pg*3 + (pj-pg)*1 WHERE pe IS NULL OR pts IS NULL;
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE rankings_grupo DROP COLUMN IF EXISTS pe;
        ALTER TABLE rankings_grupo DROP COLUMN IF EXISTS pts;
        ALTER TABLE rankings_general DROP COLUMN IF EXISTS pe;
        ALTER TABLE rankings_general DROP COLUMN IF EXISTS pts;
        ALTER TABLE categorias DROP CONSTRAINT IF EXISTS categorias_sets_x_partido_check;
        ALTER TABLE categorias ADD CONSTRAINT categorias_sets_x_partido_check CHECK (sets_x_partido IN (1,3,5));
        ALTER TABLE categorias ALTER COLUMN criterio_clasif TYPE VARCHAR(20);
    """)
