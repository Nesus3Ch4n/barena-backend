"""clasificación a siguiente ronda + llaves de bracket automáticas

- categorias.clasificacion: cómo se decide quién pasa a la siguiente ronda
  ('grupos' -> los avance_x_grupo primeros de cada grupo,
   'ranking_general' -> todas las duplas ordenadas por ranking general).
- partidos.llave: índice de la llave dentro de su fase (0 = única llave,
  la llave j alimenta la llave j//2 de la fase siguiente).
- partidos.equipo_local_id / equipo_visit_id anulables: las llaves nacen
  vacías y se llenan cuando avanza el ganador del partido previo.
- Fases de eliminación completa: 32vos/16vos/8vos/4vos/semis/final/3er puesto.

Revision ID: 008_bracket_llaves
Revises: 007_juego_limpio
Create Date: 2026-09-14
"""
from alembic import op

revision = "008_bracket_llaves"
down_revision = "007_juego_limpio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        -- Cómo se decide quién pasa a la siguiente ronda (16vos/8vos/4vos...):
        ALTER TABLE categorias ADD COLUMN IF NOT EXISTS clasificacion VARCHAR(20) NOT NULL DEFAULT 'grupos';
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_categorias_clasificacion') THEN
                ALTER TABLE categorias ADD CONSTRAINT chk_categorias_clasificacion CHECK (clasificacion IN ('grupos','ranking_general'));
            END IF;
        END $$;

        -- Índice de la llave dentro de su fase (0 = única llave / final)
        ALTER TABLE partidos ADD COLUMN IF NOT EXISTS llave INTEGER NOT NULL DEFAULT 0;

        -- Las llaves nacen sin equipo (local/visit NULL) y se llenan al avanzar el ganador
        ALTER TABLE partidos ALTER COLUMN equipo_local_id DROP NOT NULL;
        ALTER TABLE partidos ALTER COLUMN equipo_visit_id DROP NOT NULL;

        -- Fases completas de eliminación directa
        ALTER TABLE partidos DROP CONSTRAINT IF EXISTS partidos_fase_check;
        ALTER TABLE partidos ADD CONSTRAINT partidos_fase_check CHECK (fase IN ('grupos','treintaidosavos','dieciseisavos','octavos','cuartos','semi','final','tercer_puesto','ronda'));
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE categorias DROP CONSTRAINT IF EXISTS chk_categorias_clasificacion;
        ALTER TABLE categorias DROP COLUMN IF EXISTS clasificacion;
        ALTER TABLE partidos DROP COLUMN IF EXISTS llave;
        ALTER TABLE partidos ALTER COLUMN equipo_local_id SET NOT NULL;
        ALTER TABLE partidos ALTER COLUMN equipo_visit_id SET NOT NULL;
        ALTER TABLE partidos DROP CONSTRAINT IF EXISTS partidos_fase_check;
        ALTER TABLE partidos ADD CONSTRAINT partidos_fase_check CHECK (fase IN ('grupos','cuartos','semi','final','tercer_puesto'));
    """)