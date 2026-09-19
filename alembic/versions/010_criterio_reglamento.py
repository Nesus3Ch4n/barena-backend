"""criterio reglamento Amor y Amistad para todos los torneos

Aplica PG>CS>CP>JL (partidos ganados > cociente sets > cociente puntos >
juego limpio) como criterio por defecto en todas las categorias, y alinea
el ranking general con el mismo orden incluyendo sets/puntos.

Enfrentamiento directo (4to criterio del reglamento) y sorteo (5to) quedan
como decision manual del organizador (seed / edicion), sin automatizar.

Revision ID: 010_criterio_reglamento
Revises: 009_marcador_vivo
Create Date: 2026-09-19
"""
from alembic import op

revision = "010_criterio_reglamento"
down_revision = "009_marcador_vivo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        -- Columnas de cocientes en ranking general (para CS/CP)
        ALTER TABLE rankings_general ADD COLUMN IF NOT EXISTS sets_favor INTEGER DEFAULT 0;
        ALTER TABLE rankings_general ADD COLUMN IF NOT EXISTS sets_contra INTEGER DEFAULT 0;
        ALTER TABLE rankings_general ADD COLUMN IF NOT EXISTS puntos_favor INTEGER DEFAULT 0;
        ALTER TABLE rankings_general ADD COLUMN IF NOT EXISTS puntos_contra INTEGER DEFAULT 0;

        -- Default de modelo + normalizacion de criterios antiguos al reglamento
        ALTER TABLE categorias ALTER COLUMN criterio_clasif SET DEFAULT 'PG>CS>CP>JL';
        UPDATE categorias
        SET criterio_clasif = 'PG>CS>CP>JL'
        WHERE criterio_clasif IN ('PG>SF>PF>DP', 'PTS>SF>CP>JL', 'V>S>P>DP', 'PG>SF>PF>DP>PTS')
           OR criterio_clasif IS NULL OR criterio_clasif = '';

        -- Grupo: fallback al reglamento si la categoria no tiene criterio
        CREATE OR REPLACE FUNCTION fn_recalc_rankings_grupo(p_grupo_id UUID) RETURNS VOID AS $$
        DECLARE
            v_categoria_id UUID;
            v_criterio TEXT;
            v_order TEXT := '';
            v_parts TEXT[];
            v_expr TEXT;
            v_i INT;
            v_sql TEXT;
        BEGIN
            SELECT categoria_id INTO v_categoria_id FROM grupos WHERE id = p_grupo_id;
            IF v_categoria_id IS NULL THEN RETURN; END IF;

            SELECT criterio_clasif INTO v_criterio FROM categorias WHERE id = v_categoria_id;
            v_criterio := COALESCE(NULLIF(v_criterio, ''), 'PG>CS>CP>JL');
            v_parts := regexp_split_to_array(v_criterio, '>');

            FOR v_i IN 1..array_length(v_parts, 1) LOOP
                v_expr := CASE upper(btrim(v_parts[v_i]))
                    WHEN 'PG' THEN 'pg DESC'
                    WHEN 'PE' THEN 'pe DESC'
                    WHEN 'PP' THEN 'pp ASC'
                    WHEN 'PTS' THEN 'pts DESC'
                    WHEN 'SF' THEN 'sets_favor DESC'
                    WHEN 'SC' THEN 'sets_contra ASC'
                    WHEN 'PF' THEN 'puntos_favor DESC'
                    WHEN 'PC' THEN 'puntos_contra ASC'
                    WHEN 'DP' THEN '(puntos_favor - puntos_contra) DESC'
                    WHEN 'DS' THEN '(sets_favor - sets_contra) DESC'
                    WHEN 'CP' THEN 'CASE WHEN puntos_contra = 0 THEN 99999999 ELSE puntos_favor::numeric / puntos_contra END DESC'
                    WHEN 'CS' THEN 'CASE WHEN sets_contra = 0 THEN 99999999 ELSE sets_favor::numeric / sets_contra END DESC'
                    WHEN 'JL' THEN 'sanciones ASC'
                    WHEN 'V' THEN 'pg DESC'
                    WHEN 'S' THEN 'sets_favor DESC'
                    WHEN 'P' THEN 'puntos_favor DESC'
                    WHEN 'SG' THEN 'sets_favor DESC'
                    WHEN 'PPG' THEN 'CASE WHEN pj = 0 THEN 0 ELSE puntos_favor::numeric / pj END DESC'
                    ELSE NULL
                END;
                IF v_expr IS NOT NULL THEN
                    IF v_order <> '' THEN v_order := v_order || ', '; END IF;
                    v_order := v_order || v_expr;
                END IF;
            END LOOP;
            IF v_order = '' THEN v_order := 'pg DESC, CASE WHEN sets_contra = 0 THEN 99999999 ELSE sets_favor::numeric / sets_contra END DESC, CASE WHEN puntos_contra = 0 THEN 99999999 ELSE puntos_favor::numeric / puntos_contra END DESC, sanciones ASC'; END IF;
            v_order := v_order || ', equipo_id';

            DELETE FROM rankings_grupo WHERE grupo_id = p_grupo_id;

            v_sql := format($sql$
                INSERT INTO rankings_grupo (grupo_id, equipo_id, pj, pg, pp, pe, pts, sets_favor, sets_contra, puntos_favor, puntos_contra, sanciones, posicion)
                WITH equipos_grupo AS (
                    SELECT id FROM equipos WHERE grupo_id = %L AND estado != 'eliminado'
                ),
                partidos_grupo AS (
                    SELECT * FROM partidos WHERE grupo_id = %L AND estado = 'finalizado'
                ),
                stats_por_equipo AS (
                    SELECT
                        e.id as equipo_id,
                        COUNT(p.id) as pj,
                        COUNT(CASE WHEN p.ganador_id = e.id THEN 1 END) as pg,
                        COUNT(CASE WHEN p.id IS NOT NULL AND p.ganador_id IS NULL THEN 1 END) as pe,
                        (SELECT COUNT(*) FROM sets_partido s JOIN partidos pp ON s.partido_id=pp.id WHERE pp.id IN (SELECT id FROM partidos_grupo) AND s.ganador_id = e.id) as sets_favor,
                        (SELECT COUNT(*) FROM sets_partido s JOIN partidos pp ON s.partido_id=pp.id WHERE (pp.id IN (SELECT id FROM partidos_grupo)) AND (pp.equipo_local_id=e.id OR pp.equipo_visit_id=e.id) AND s.ganador_id IS NOT NULL) as total_sets_equipo,
                        COALESCE((SELECT SUM(CASE WHEN pp.equipo_local_id=e.id THEN s.pts_local ELSE s.pts_visitante END) FROM sets_partido s JOIN partidos pp ON s.partido_id=pp.id WHERE pp.id IN (SELECT id FROM partidos_grupo WHERE equipo_local_id=e.id OR equipo_visit_id=e.id)),0) as puntos_favor,
                        COALESCE((SELECT SUM(CASE WHEN pp.equipo_local_id=e.id THEN s.pts_visitante ELSE s.pts_local END) FROM sets_partido s JOIN partidos pp ON s.partido_id=pp.id WHERE pp.id IN (SELECT id FROM partidos_grupo WHERE equipo_local_id=e.id OR equipo_visit_id=e.id)),0) as puntos_contra,
                        COALESCE((SELECT SUM(CASE WHEN pp.equipo_local_id=e.id THEN (COALESCE(pp.tarjetas_amarillas_local,0) + COALESCE(pp.tarjetas_rojas_local,0)) ELSE (COALESCE(pp.tarjetas_amarillas_visit,0) + COALESCE(pp.tarjetas_rojas_visit,0)) END) FROM partidos pp WHERE pp.id IN (SELECT id FROM partidos_grupo WHERE equipo_local_id=e.id OR equipo_visit_id=e.id)),0) as sanciones
                    FROM equipos_grupo e
                    LEFT JOIN partidos_grupo p ON p.equipo_local_id=e.id OR p.equipo_visit_id=e.id
                    GROUP BY e.id
                ),
                con_pp AS (
                    SELECT equipo_id, pj, pg, pe, (pj - pg - pe) as pp,
                           (pg*3 + pe*2 + (pj - pg - pe)*1) as pts,
                           sets_favor, (total_sets_equipo - sets_favor) as sets_contra,
                           puntos_favor, puntos_contra, sanciones
                    FROM stats_por_equipo
                )
                SELECT %L, equipo_id, pj, pg, pp, pe, pts, sets_favor, sets_contra, puntos_favor, puntos_contra, sanciones,
                       ROW_NUMBER() OVER (ORDER BY %s)
                FROM con_pp;
            $sql$, p_grupo_id, p_grupo_id, p_grupo_id, v_order);
            EXECUTE v_sql;
        END;
        $$ LANGUAGE plpgsql;

        -- General: mismo criterio PG>CS>CP>JL con sets/puntos poblados
        CREATE OR REPLACE FUNCTION fn_recalc_rankings_general(p_categoria_id UUID) RETURNS VOID AS $$
        BEGIN
            DELETE FROM rankings_general WHERE categoria_id = p_categoria_id;
            INSERT INTO rankings_general (categoria_id, equipo_id, pj, pg, pp, pe, pts, sets_favor, sets_contra, puntos_favor, puntos_contra, sanciones, posicion)
            WITH equipos_cat AS (
                SELECT id FROM equipos WHERE categoria_id = p_categoria_id AND estado != 'eliminado'
            ),
            partidos_cat AS (
                SELECT * FROM partidos WHERE categoria_id = p_categoria_id AND estado = 'finalizado'
            ),
            stats_por_equipo AS (
                SELECT
                    e.id as equipo_id,
                    COUNT(p.id) as pj,
                    COUNT(CASE WHEN p.ganador_id = e.id THEN 1 END) as pg,
                    COUNT(CASE WHEN p.id IS NOT NULL AND p.ganador_id IS NULL THEN 1 END) as pe,
                    COALESCE((SELECT COUNT(*) FROM sets_partido s JOIN partidos pp ON s.partido_id=pp.id WHERE pp.categoria_id = p_categoria_id AND pp.estado='finalizado' AND (pp.equipo_local_id=e.id OR pp.equipo_visit_id=e.id) AND s.ganador_id = e.id),0) as sets_favor,
                    COALESCE((SELECT COUNT(*) FROM sets_partido s JOIN partidos pp ON s.partido_id=pp.id WHERE pp.categoria_id = p_categoria_id AND pp.estado='finalizado' AND (pp.equipo_local_id=e.id OR pp.equipo_visit_id=e.id) AND s.ganador_id IS NOT NULL),0) as total_sets_equipo,
                    COALESCE((SELECT SUM(CASE WHEN pp.equipo_local_id=e.id THEN s.pts_local ELSE s.pts_visitante END) FROM sets_partido s JOIN partidos pp ON s.partido_id=pp.id WHERE pp.categoria_id = p_categoria_id AND pp.estado='finalizado' AND (pp.equipo_local_id=e.id OR pp.equipo_visit_id=e.id)),0) as puntos_favor,
                    COALESCE((SELECT SUM(CASE WHEN pp.equipo_local_id=e.id THEN s.pts_visitante ELSE s.pts_local END) FROM sets_partido s JOIN partidos pp ON s.partido_id=pp.id WHERE pp.categoria_id = p_categoria_id AND pp.estado='finalizado' AND (pp.equipo_local_id=e.id OR pp.equipo_visit_id=e.id)),0) as puntos_contra,
                    COALESCE((SELECT SUM(CASE WHEN pp.equipo_local_id=e.id THEN (COALESCE(pp.tarjetas_amarillas_local,0) + COALESCE(pp.tarjetas_rojas_local,0)) ELSE (COALESCE(pp.tarjetas_amarillas_visit,0) + COALESCE(pp.tarjetas_rojas_visit,0)) END) FROM partidos pp WHERE pp.categoria_id = p_categoria_id AND pp.estado='finalizado' AND (pp.equipo_local_id=e.id OR pp.equipo_visit_id=e.id)),0) as sanciones
                FROM equipos_cat e
                LEFT JOIN partidos_cat p ON p.equipo_local_id=e.id OR p.equipo_visit_id=e.id
                GROUP BY e.id
            ),
            con_pp AS (
                SELECT equipo_id, pj, pg, pe, (pj - pg - pe) as pp,
                       (pg*3 + pe*2 + (pj - pg - pe)*1) as pts,
                       sets_favor, (total_sets_equipo - sets_favor) as sets_contra,
                       puntos_favor, puntos_contra, sanciones
                FROM stats_por_equipo
            )
            SELECT p_categoria_id, equipo_id, pj, pg, pp, pe, pts, sets_favor, sets_contra, puntos_favor, puntos_contra, sanciones,
                   ROW_NUMBER() OVER (ORDER BY pg DESC,
                       CASE WHEN sets_contra = 0 THEN 99999999 ELSE sets_favor::numeric / sets_contra END DESC,
                       CASE WHEN puntos_contra = 0 THEN 99999999 ELSE puntos_favor::numeric / puntos_contra END DESC,
                       sanciones ASC, equipo_id)
            FROM con_pp;
        END;
        $$ LANGUAGE plpgsql;

        -- Recalcular rankings existentes con el nuevo criterio
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN SELECT id FROM grupos LOOP
                PERFORM fn_recalc_rankings_grupo(r.id);
            END LOOP;
            FOR r IN SELECT id FROM categorias LOOP
                PERFORM fn_recalc_rankings_general(r.id);
            END LOOP;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE categorias ALTER COLUMN criterio_clasif SET DEFAULT 'PTS>SF>CP>JL';
    """)
