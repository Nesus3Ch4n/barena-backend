"""add ranking_general and bracket_tipo to categorias + bracket_tipo to partidos

Revision ID: 003_categoria_brackets
Revises: 002_refresh_tokens
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa

revision = "003_categoria_brackets"
down_revision = "002_refresh_tokens"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
        ALTER TABLE categorias ADD COLUMN IF NOT EXISTS ranking_general_enabled BOOLEAN DEFAULT TRUE;
        ALTER TABLE categorias ADD COLUMN IF NOT EXISTS bracket_tipo VARCHAR(20) DEFAULT 'general';
        -- constraint for bracket_tipo
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_categorias_bracket_tipo') THEN
                ALTER TABLE categorias ADD CONSTRAINT chk_categorias_bracket_tipo CHECK (bracket_tipo IN ('general','diamante','oro','diamante_oro'));
            END IF;
        END $$;
        ALTER TABLE partidos ADD COLUMN IF NOT EXISTS bracket_tipo VARCHAR(20) DEFAULT 'general';
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_partidos_bracket_tipo') THEN
                ALTER TABLE partidos ADD CONSTRAINT chk_partidos_bracket_tipo CHECK (bracket_tipo IN ('general','diamante','oro'));
            END IF;
        END $$;
        UPDATE categorias SET ranking_general_enabled=TRUE WHERE ranking_general_enabled IS NULL;
        UPDATE categorias SET bracket_tipo='general' WHERE bracket_tipo IS NULL;
        UPDATE partidos SET bracket_tipo='general' WHERE bracket_tipo IS NULL;
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE categorias DROP COLUMN IF EXISTS ranking_general_enabled;
        ALTER TABLE categorias DROP COLUMN IF EXISTS bracket_tipo;
        ALTER TABLE partidos DROP COLUMN IF EXISTS bracket_tipo;
    """)
