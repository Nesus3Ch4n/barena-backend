"""initial 19 tables + RLS + triggers rankings + seed

Revision ID: 001_initial
Revises: 
Create Date: 2026-09-05

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")

    # ---------- USUARIOS ----------
    op.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email VARCHAR(255) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        nombre_completo VARCHAR(120) NOT NULL,
        avatar_url VARCHAR(500),
        telefono VARCHAR(20),
        doc_identidad VARCHAR(30),
        fecha_nacimiento DATE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS roles (
        id VARCHAR(30) PRIMARY KEY,
        descripcion VARCHAR(120)
    );
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS user_roles (
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role_id VARCHAR(30) NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
        asignado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, role_id)
    );
    """)

    # ---------- CATALOGO ----------
    op.execute("""
    CREATE TABLE IF NOT EXISTS deportes (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        nombre VARCHAR(50) NOT NULL UNIQUE,
        icono VARCHAR(30),
        config_stats JSONB,
        activo BOOLEAN NOT NULL DEFAULT true
    );
    """)

    # ---------- TORNEO CORE ----------
    op.execute("""
    CREATE TABLE IF NOT EXISTS torneos (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        nombre VARCHAR(120) NOT NULL,
        slug VARCHAR(120) NOT NULL UNIQUE,
        deporte_id UUID NOT NULL REFERENCES deportes(id),
        organizador_id UUID NOT NULL REFERENCES users(id),
        fecha_inicio DATE,
        fecha_fin DATE,
        sede VARCHAR(120),
        ciudad VARCHAR(80),
        coords POINT,
        estado VARCHAR(20) NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador','activo','finalizado')),
        publico BOOLEAN NOT NULL DEFAULT false,
        config_visibilidad JSONB NOT NULL DEFAULT '{"fixture_visible": false, "grupos_visible": false, "posiciones_visible": false, "stats_visible": true, "ranking_visible": false}'::jsonb,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
        CHECK (fecha_fin IS NULL OR fecha_inicio IS NULL OR fecha_fin >= fecha_inicio)
    );
    CREATE INDEX IF NOT EXISTS idx_torneos_slug ON torneos(slug);
    CREATE INDEX IF NOT EXISTS idx_torneos_organizador ON torneos(organizador_id);
    CREATE INDEX IF NOT EXISTS idx_torneos_estado ON torneos(estado);
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS ramas (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        torneo_id UUID NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
        tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('masc','fem','mixto')),
        nombre_custom VARCHAR(50),
        activa BOOLEAN NOT NULL DEFAULT true
    );
    CREATE INDEX IF NOT EXISTS idx_ramas_torneo ON ramas(torneo_id);
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS categorias (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        rama_id UUID NOT NULL REFERENCES ramas(id) ON DELETE CASCADE,
        nombre VARCHAR(50) NOT NULL,
        formato VARCHAR(20) NOT NULL DEFAULT 'grupos' CHECK (formato IN ('grupos','eliminatoria','round_robin','custom')),
        cuadro_perdedores BOOLEAN NOT NULL DEFAULT false,
        equipos_x_grupo INTEGER NOT NULL DEFAULT 4 CHECK (equipos_x_grupo BETWEEN 2 AND 8),
        sets_x_partido INTEGER NOT NULL DEFAULT 3 CHECK (sets_x_partido IN (1,3,5)),
        puntos_x_set INTEGER NOT NULL DEFAULT 21 CHECK (puntos_x_set IN (15,21,25)),
        avance_x_grupo INTEGER NOT NULL DEFAULT 2 CHECK (avance_x_grupo BETWEEN 1 AND 4),
        criterio_clasif VARCHAR(20) NOT NULL DEFAULT 'V>S>P>DP'
    );
    CREATE INDEX IF NOT EXISTS idx_categorias_rama ON categorias(rama_id);
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS grupos (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        categoria_id UUID NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
        nombre VARCHAR(10) NOT NULL,
        orden INTEGER NOT NULL DEFAULT 1,
        UNIQUE(categoria_id, nombre)
    );
    CREATE INDEX IF NOT EXISTS idx_grupos_categoria ON grupos(categoria_id);
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS equipos (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        categoria_id UUID NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
        grupo_id UUID REFERENCES grupos(id) ON DELETE SET NULL,
        nombre VARCHAR(80) NOT NULL,
        ciudad VARCHAR(80),
        foto_url VARCHAR(500),
        estado VARCHAR(20) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','aprobado','eliminado')),
        seed INTEGER CHECK (seed IS NULL OR seed > 0),
        inscrito_en TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_equipos_categoria ON equipos(categoria_id);
    CREATE INDEX IF NOT EXISTS idx_equipos_grupo ON equipos(grupo_id);
    CREATE INDEX IF NOT EXISTS idx_equipos_estado ON equipos(estado);
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS atletas (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        equipo_id UUID NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
        user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        nombre_completo VARCHAR(120) NOT NULL,
        posicion VARCHAR(20) NOT NULL DEFAULT 'titular' CHECK (posicion IN ('titular','libero')),
        foto_url VARCHAR(500),
        doc_identidad VARCHAR(30),
        fecha_nacimiento DATE,
        codigo_reclamo VARCHAR(8) UNIQUE
    );
    CREATE INDEX IF NOT EXISTS idx_atletas_equipo ON atletas(equipo_id);
    CREATE INDEX IF NOT EXISTS idx_atletas_user ON atletas(user_id);
    CREATE INDEX IF NOT EXISTS idx_atletas_codigo ON atletas(codigo_reclamo);
    """)

    # ---------- COMPETICION ----------
    op.execute("""
    CREATE TABLE IF NOT EXISTS partidos (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        categoria_id UUID NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
        grupo_id UUID REFERENCES grupos(id) ON DELETE SET NULL,
        fase VARCHAR(20) NOT NULL DEFAULT 'grupos' CHECK (fase IN ('grupos','cuartos','semi','final','tercer_puesto')),
        equipo_local_id UUID NOT NULL REFERENCES equipos(id),
        equipo_visit_id UUID NOT NULL REFERENCES equipos(id),
        cancha VARCHAR(50),
        fecha_hora TIMESTAMPTZ,
        estado VARCHAR(20) NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','en_juego','finalizado')),
        ganador_id UUID REFERENCES equipos(id),
        es_cuadro_perdedores BOOLEAN NOT NULL DEFAULT false,
        arbitro_id UUID REFERENCES users(id) ON DELETE SET NULL,
        CHECK (equipo_local_id != equipo_visit_id)
    );
    CREATE INDEX IF NOT EXISTS idx_partidos_categoria ON partidos(categoria_id);
    CREATE INDEX IF NOT EXISTS idx_partidos_grupo ON partidos(grupo_id);
    CREATE INDEX IF NOT EXISTS idx_partidos_fecha ON partidos(fecha_hora);
    CREATE INDEX IF NOT EXISTS idx_partidos_estado ON partidos(estado);
    CREATE INDEX IF NOT EXISTS idx_partidos_categoria_fase ON partidos(categoria_id, fase);
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS sets_partido (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        partido_id UUID NOT NULL REFERENCES partidos(id) ON DELETE CASCADE,
        numero_set INTEGER NOT NULL CHECK (numero_set BETWEEN 1 AND 5),
        pts_local INTEGER NOT NULL CHECK (pts_local >= 0),
        pts_visitante INTEGER NOT NULL CHECK (pts_visitante >= 0),
        ganador_id UUID REFERENCES equipos(id),
        duracion_min INTEGER CHECK (duracion_min IS NULL OR duracion_min > 0),
        UNIQUE(partido_id, numero_set)
    );
    CREATE INDEX IF NOT EXISTS idx_sets_partido ON sets_partido(partido_id);
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS estadisticas_atleta (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        atleta_id UUID NOT NULL REFERENCES atletas(id) ON DELETE CASCADE,
        partido_id UUID NOT NULL REFERENCES partidos(id) ON DELETE CASCADE,
        ataques_pts INTEGER NOT NULL DEFAULT 0 CHECK (ataques_pts >= 0),
        bloqueos_pts INTEGER NOT NULL DEFAULT 0 CHECK (bloqueos_pts >= 0),
        saques_directos INTEGER NOT NULL DEFAULT 0 CHECK (saques_directos >= 0),
        errores_propios INTEGER NOT NULL DEFAULT 0 CHECK (errores_propios >= 0),
        defensas_dig INTEGER NOT NULL DEFAULT 0 CHECK (defensas_dig >= 0),
        recepciones_perf INTEGER NOT NULL DEFAULT 0 CHECK (recepciones_perf >= 0),
        ataques_total INTEGER NOT NULL DEFAULT 0 CHECK (ataques_total >= 0),
        saques_total INTEGER NOT NULL DEFAULT 0 CHECK (saques_total >= 0),
        puntos_total INTEGER GENERATED ALWAYS AS (ataques_pts + bloqueos_pts + saques_directos) STORED,
        UNIQUE(atleta_id, partido_id)
    );
    CREATE INDEX IF NOT EXISTS idx_est_atleta ON estadisticas_atleta(atleta_id);
    CREATE INDEX IF NOT EXISTS idx_est_partido ON estadisticas_atleta(partido_id);
    """)

    # ---------- RANKINGS ----------
    op.execute("""
    CREATE TABLE IF NOT EXISTS rankings_grupo (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        grupo_id UUID NOT NULL REFERENCES grupos(id) ON DELETE CASCADE,
        equipo_id UUID NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
        pj INTEGER NOT NULL DEFAULT 0,
        pg INTEGER NOT NULL DEFAULT 0,
        pp INTEGER NOT NULL DEFAULT 0,
        sets_favor INTEGER NOT NULL DEFAULT 0,
        sets_contra INTEGER NOT NULL DEFAULT 0,
        puntos_favor INTEGER NOT NULL DEFAULT 0,
        puntos_contra INTEGER NOT NULL DEFAULT 0,
        posicion INTEGER NOT NULL DEFAULT 0,
        UNIQUE(grupo_id, equipo_id)
    );
    CREATE INDEX IF NOT EXISTS idx_rankings_grupo_pos ON rankings_grupo(grupo_id, posicion);
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS rankings_general (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        categoria_id UUID NOT NULL REFERENCES categorias(id) ON DELETE CASCADE,
        equipo_id UUID NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
        pj INTEGER NOT NULL DEFAULT 0,
        pg INTEGER NOT NULL DEFAULT 0,
        pp INTEGER NOT NULL DEFAULT 0,
        posicion INTEGER NOT NULL DEFAULT 0,
        UNIQUE(categoria_id, equipo_id)
    );
    CREATE INDEX IF NOT EXISTS idx_rankings_general_pos ON rankings_general(categoria_id, posicion);
    """)

    # ---------- SISTEMA ----------
    op.execute("""
    CREATE TABLE IF NOT EXISTS notificaciones (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        torneo_id UUID NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
        atleta_id UUID REFERENCES atletas(id) ON DELETE CASCADE,
        tipo VARCHAR(30) NOT NULL CHECK (tipo IN ('proximo_partido','resultado','cambio_horario','general')),
        titulo VARCHAR(120) NOT NULL,
        mensaje VARCHAR(500) NOT NULL,
        canal VARCHAR(20) NOT NULL DEFAULT 'in_app' CHECK (canal IN ('push','whatsapp','in_app')),
        enviada BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_notis_torneo ON notificaciones(torneo_id);
    CREATE INDEX IF NOT EXISTS idx_notis_atleta ON notificaciones(atleta_id);
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS auditoria (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        accion VARCHAR(30) NOT NULL CHECK (accion IN ('CREATE','UPDATE','DELETE','PUBLICAR','APROBAR','RECHAZAR')),
        entidad VARCHAR(30) NOT NULL,
        entidad_id UUID,
        detalle JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_auditoria_entidad ON auditoria(entidad, entidad_id);
    CREATE INDEX IF NOT EXISTS idx_auditoria_user ON auditoria(user_id);
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS config_global (
        clave VARCHAR(50) PRIMARY KEY,
        valor JSONB NOT NULL,
        actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS reportes_cache (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        torneo_id UUID NOT NULL REFERENCES torneos(id) ON DELETE CASCADE,
        tipo VARCHAR(30) NOT NULL CHECK (tipo IN ('fixture','posiciones','stats_equipo','stats_atleta','ranking_general','bracket')),
        params JSONB,
        pdf_url VARCHAR(500),
        generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        expira_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '5 minutes'
    );
    CREATE INDEX IF NOT EXISTS idx_reportes_torneo ON reportes_cache(torneo_id, tipo);
    """)

    # ---------- RLS HELPERS ----------
    op.execute("""
    CREATE OR REPLACE FUNCTION current_user_id() RETURNS UUID AS $$
    BEGIN
        RETURN NULLIF(current_setting('app.current_user_id', true), '')::UUID;
    EXCEPTION WHEN others THEN RETURN NULL;
    END;
    $$ LANGUAGE plpgsql STABLE;

    CREATE OR REPLACE FUNCTION is_super_admin() RETURNS BOOLEAN AS $$
    BEGIN
        RETURN EXISTS (
            SELECT 1 FROM user_roles
            WHERE user_id = current_user_id() AND role_id = 'super_admin'
        );
    END;
    $$ LANGUAGE plpgsql STABLE;

    CREATE OR REPLACE FUNCTION is_organizador(t UUID) RETURNS BOOLEAN AS $$
    BEGIN
        RETURN EXISTS (SELECT 1 FROM torneos WHERE id = t AND organizador_id = current_user_id()) OR is_super_admin();
    END;
    $$ LANGUAGE plpgsql STABLE;
    """)

    # Enable RLS on core tables
    for tbl in ["torneos","ramas","categorias","grupos","equipos","atletas","partidos","sets_partido","estadisticas_atleta","rankings_grupo","rankings_general","notificaciones","auditoria","reportes_cache"]:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")

    # Policies (permissive for service_role via is_super_admin, restrictive for anon)
    op.execute("""
    -- torneos: organizador own + public read
    DROP POLICY IF EXISTS p_torneos_all ON torneos;
    CREATE POLICY p_torneos_all ON torneos FOR ALL USING (organizador_id = current_user_id() OR is_super_admin() OR publico = true) WITH CHECK (organizador_id = current_user_id() OR is_super_admin());
    -- ramas/categorias/grupos via torneo
    DROP POLICY IF EXISTS p_ramas_all ON ramas;
    CREATE POLICY p_ramas_all ON ramas FOR ALL USING (is_organizador(torneo_id) OR EXISTS (SELECT 1 FROM torneos t WHERE t.id = torneo_id AND t.publico = true));
    DROP POLICY IF EXISTS p_categorias_all ON categorias;
    CREATE POLICY p_categorias_all ON categorias FOR ALL USING (EXISTS (SELECT 1 FROM ramas r JOIN torneos t ON r.torneo_id=t.id WHERE r.id=rama_id AND (t.organizador_id=current_user_id() OR is_super_admin() OR t.publico=true)));
    -- equipos/atletas: similar via categoria -> rama -> torneo
    DROP POLICY IF EXISTS p_equipos_all ON equipos;
    CREATE POLICY p_equipos_all ON equipos FOR ALL USING (
        EXISTS (SELECT 1 FROM categorias c JOIN ramas r ON c.rama_id=r.id JOIN torneos t ON r.torneo_id=t.id WHERE c.id=categoria_id AND (t.organizador_id=current_user_id() OR is_super_admin() OR t.publico=true))
    );
    DROP POLICY IF EXISTS p_atletas_all ON atletas;
    CREATE POLICY p_atletas_all ON atletas FOR ALL USING (
        EXISTS (SELECT 1 FROM equipos e JOIN categorias c ON e.categoria_id=c.id JOIN ramas r ON c.rama_id=r.id JOIN torneos t ON r.torneo_id=t.id WHERE e.id=equipo_id AND (t.organizador_id=current_user_id() OR is_super_admin() OR t.publico=true))
    );
    -- partidos
    DROP POLICY IF EXISTS p_partidos_all ON partidos;
    CREATE POLICY p_partidos_all ON partidos FOR ALL USING (
        EXISTS (SELECT 1 FROM categorias c JOIN ramas r ON c.rama_id=r.id JOIN torneos t ON r.torneo_id=t.id WHERE c.id=categoria_id AND (t.organizador_id=current_user_id() OR is_super_admin() OR t.publico=true))
    );
    -- sets, stats, rankings
    DROP POLICY IF EXISTS p_sets_all ON sets_partido;
    CREATE POLICY p_sets_all ON sets_partido FOR ALL USING (
        EXISTS (SELECT 1 FROM partidos p JOIN categorias c ON p.categoria_id=c.id JOIN ramas r ON c.rama_id=r.id JOIN torneos t ON r.torneo_id=t.id WHERE p.id=partido_id AND (t.organizador_id=current_user_id() OR is_super_admin() OR t.publico=true))
    );
    DROP POLICY IF EXISTS p_est_all ON estadisticas_atleta;
    CREATE POLICY p_est_all ON estadisticas_atleta FOR ALL USING (
        EXISTS (SELECT 1 FROM partidos p JOIN categorias c ON p.categoria_id=c.id JOIN ramas r ON c.rama_id=r.id JOIN torneos t ON r.torneo_id=t.id WHERE p.id=partido_id AND (t.organizador_id=current_user_id() OR is_super_admin() OR t.publico=true))
    );
    DROP POLICY IF EXISTS p_rg_all ON rankings_grupo;
    CREATE POLICY p_rg_all ON rankings_grupo FOR ALL USING (
        EXISTS (SELECT 1 FROM grupos g JOIN categorias c ON g.categoria_id=c.id JOIN ramas r ON c.rama_id=r.id JOIN torneos t ON r.torneo_id=t.id WHERE g.id=grupo_id AND (t.organizador_id=current_user_id() OR is_super_admin() OR t.publico=true))
    );
    DROP POLICY IF EXISTS p_rgen_all ON rankings_general;
    CREATE POLICY p_rgen_all ON rankings_general FOR ALL USING (
        EXISTS (SELECT 1 FROM categorias c JOIN ramas r ON c.rama_id=r.id JOIN torneos t ON r.torneo_id=t.id WHERE c.id=categoria_id AND (t.organizador_id=current_user_id() OR is_super_admin() OR t.publico=true))
    );
    -- auditoria solo super_admin read
    DROP POLICY IF EXISTS p_auditoria_all ON auditoria;
    CREATE POLICY p_auditoria_all ON auditoria FOR ALL USING (is_super_admin());
    """)

    # ---------- TRIGGERS RANKINGS ----------
    op.execute("""
    -- Funcion recalc grupo: V > S > P > DP
    CREATE OR REPLACE FUNCTION fn_recalc_rankings_grupo(p_grupo_id UUID) RETURNS VOID AS $$
    DECLARE
        v_categoria_id UUID;
    BEGIN
        SELECT categoria_id INTO v_categoria_id FROM grupos WHERE id = p_grupo_id;
        IF v_categoria_id IS NULL THEN RETURN; END IF;

        -- Borra y recalcula
        DELETE FROM rankings_grupo WHERE grupo_id = p_grupo_id;

        INSERT INTO rankings_grupo (grupo_id, equipo_id, pj, pg, pp, sets_favor, sets_contra, puntos_favor, puntos_contra, posicion)
        WITH equipos_grupo AS (
            SELECT id FROM equipos WHERE grupo_id = p_grupo_id AND estado != 'eliminado'
        ),
        partidos_grupo AS (
            SELECT * FROM partidos WHERE grupo_id = p_grupo_id AND estado = 'finalizado'
        ),
        stats_por_equipo AS (
            SELECT
                e.id as equipo_id,
                COUNT(p.id) as pj,
                COUNT(CASE WHEN p.ganador_id = e.id THEN 1 END) as pg,
                -- sets
                (SELECT COUNT(*) FROM sets_partido s JOIN partidos pp ON s.partido_id=pp.id WHERE pp.id IN (SELECT id FROM partidos_grupo) AND s.ganador_id = e.id) as sets_favor,
                (SELECT COUNT(*) FROM sets_partido s JOIN partidos pp ON s.partido_id=pp.id WHERE pp.id IN (SELECT id FROM partidos_grupo) AND s.partido_id IN (SELECT id FROM partidos_grupo WHERE equipo_local_id=e.id OR equipo_visit_id=e.id) AND s.ganador_id IS NOT NULL) as total_sets_equipo,
                -- puntos
                COALESCE((SELECT SUM(CASE WHEN pp.equipo_local_id=e.id THEN s.pts_local ELSE s.pts_visitante END) FROM sets_partido s JOIN partidos pp ON s.partido_id=pp.id WHERE pp.id IN (SELECT id FROM partidos_grupo WHERE equipo_local_id=e.id OR equipo_visit_id=e.id)),0) as puntos_favor,
                COALESCE((SELECT SUM(CASE WHEN pp.equipo_local_id=e.id THEN s.pts_visitante ELSE s.pts_local END) FROM sets_partido s JOIN partidos pp ON s.partido_id=pp.id WHERE pp.id IN (SELECT id FROM partidos_grupo WHERE equipo_local_id=e.id OR equipo_visit_id=e.id)),0) as puntos_contra
            FROM equipos_grupo e
            LEFT JOIN partidos_grupo p ON p.equipo_local_id=e.id OR p.equipo_visit_id=e.id
            GROUP BY e.id
        ),
        con_pp AS (
            SELECT equipo_id, pj, pg, (pj - pg) as pp, sets_favor, (total_sets_equipo - sets_favor) as sets_contra, puntos_favor, puntos_contra
            FROM stats_por_equipo
        )
        SELECT p_grupo_id, equipo_id, pj, pg, pp, sets_favor, sets_contra, puntos_favor, puntos_contra,
               ROW_NUMBER() OVER (ORDER BY pg DESC, sets_favor DESC, puntos_favor DESC, (puntos_favor - puntos_contra) DESC, equipo_id)
        FROM con_pp;
    END;
    $$ LANGUAGE plpgsql;

    CREATE OR REPLACE FUNCTION fn_recalc_rankings_general(p_categoria_id UUID) RETURNS VOID AS $$
    BEGIN
        DELETE FROM rankings_general WHERE categoria_id = p_categoria_id;
        INSERT INTO rankings_general (categoria_id, equipo_id, pj, pg, pp, posicion)
        WITH equipos_cat AS (
            SELECT id FROM equipos WHERE categoria_id = p_categoria_id AND estado != 'eliminado'
        ),
        partidos_cat AS (
            SELECT * FROM partidos WHERE categoria_id = p_categoria_id AND estado = 'finalizado'
        )
        SELECT p_categoria_id, e.id,
               COUNT(p.id) as pj,
               COUNT(CASE WHEN p.ganador_id = e.id THEN 1 END) as pg,
               COUNT(p.id) - COUNT(CASE WHEN p.ganador_id = e.id THEN 1 END) as pp,
               ROW_NUMBER() OVER (ORDER BY COUNT(CASE WHEN p.ganador_id = e.id THEN 1 END) DESC, COUNT(p.id) DESC, e.id)
        FROM equipos_cat e
        LEFT JOIN partidos_cat p ON p.equipo_local_id=e.id OR p.equipo_visit_id=e.id
        GROUP BY e.id;
    END;
    $$ LANGUAGE plpgsql;

    -- Trigger wrapper
    CREATE OR REPLACE FUNCTION trg_recalc_rankings() RETURNS TRIGGER AS $$
    DECLARE
        v_grupo_id UUID;
        v_categoria_id UUID;
    BEGIN
        -- Determinar ids
        IF TG_OP = 'DELETE' THEN
            v_grupo_id := OLD.grupo_id;
            v_categoria_id := OLD.categoria_id;
        ELSE
            v_grupo_id := NEW.grupo_id;
            v_categoria_id := NEW.categoria_id;
        END IF;

        -- Solo recalcular si hay cambio relevante
        IF v_grupo_id IS NOT NULL THEN
            PERFORM fn_recalc_rankings_grupo(v_grupo_id);
        END IF;
        IF v_categoria_id IS NOT NULL THEN
            PERFORM fn_recalc_rankings_general(v_categoria_id);
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    -- Triggers en partidos
    DROP TRIGGER IF EXISTS trg_rankings_partidos ON partidos;
    CREATE TRIGGER trg_rankings_partidos
    AFTER INSERT OR UPDATE OF estado, ganador_id OR DELETE ON partidos
    FOR EACH ROW EXECUTE FUNCTION trg_recalc_rankings();

    -- Triggers en sets_partido (cambia puntos/sets)
    DROP TRIGGER IF EXISTS trg_rankings_sets ON sets_partido;
    CREATE TRIGGER trg_rankings_sets
    AFTER INSERT OR UPDATE OR DELETE ON sets_partido
    FOR EACH ROW EXECUTE FUNCTION trg_recalc_rankings_from_set();

    -- Helper para sets: necesita categoria/grupo via partido
    CREATE OR REPLACE FUNCTION trg_recalc_rankings_from_set() RETURNS TRIGGER AS $$
    DECLARE
        v_grupo_id UUID;
        v_categoria_id UUID;
        v_partido_id UUID;
    BEGIN
        IF TG_OP = 'DELETE' THEN v_partido_id := OLD.partido_id; ELSE v_partido_id := NEW.partido_id; END IF;
        SELECT grupo_id, categoria_id INTO v_grupo_id, v_categoria_id FROM partidos WHERE id = v_partido_id;
        IF v_grupo_id IS NOT NULL THEN PERFORM fn_recalc_rankings_grupo(v_grupo_id); END IF;
        IF v_categoria_id IS NOT NULL THEN PERFORM fn_recalc_rankings_general(v_categoria_id); END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_rankings_sets ON sets_partido;
    CREATE TRIGGER trg_rankings_sets
    AFTER INSERT OR UPDATE OR DELETE ON sets_partido
    FOR EACH ROW EXECUTE FUNCTION trg_recalc_rankings_from_set();
    """)

    # Fix duplicate trigger creation - ensure clean
    op.execute("DROP TRIGGER IF EXISTS trg_rankings_sets ON sets_partido; CREATE TRIGGER trg_rankings_sets AFTER INSERT OR UPDATE OR DELETE ON sets_partido FOR EACH ROW EXECUTE FUNCTION trg_recalc_rankings_from_set();")

    # ---------- SEED ----------
    op.execute("""
    INSERT INTO roles (id, descripcion) VALUES
        ('super_admin', 'Administrador plataforma global'),
        ('organizador', 'Organizador dueño de torneo'),
        ('juez_anotador', 'Juez en cancha, ingreso marcador'),
        ('atleta', 'Competidor auto-registrado')
    ON CONFLICT (id) DO NOTHING;

    INSERT INTO deportes (nombre, icono, config_stats) VALUES
        ('volei_playa', 'volleyball', '{"stats": ["ATK","BLK","ACE","DIG","REC","EFT_ATK","EFT_SAQ"], "jugadores_por_equipo": 2, "libero_opcional": true}'::jsonb)
    ON CONFLICT (nombre) DO NOTHING;

    INSERT INTO config_global (clave, valor) VALUES
        ('freemium', '{"enabled": true}'::jsonb),
        ('realtime_enabled', 'true'::jsonb),
        ('max_torneos_por_organizador', '5'::jsonb),
        ('reportes_cache_ttl', '300'::jsonb)
    ON CONFLICT (clave) DO NOTHING;
    """)

    # Seed super_admin de prueba (password hash bcrypt para 'admin123' - cambiar en prod)
    op.execute("""
    -- super_admin de pruebas: email admin@servetrack.test / pass Admin123!
    -- hash generado con python passlib: $2b$12$...
    -- Se inserta solo si no existe, permite pruebas sin DATABASE_URL real
    INSERT INTO users (id, email, password_hash) VALUES
        ('00000000-0000-0000-0000-000000000001', 'admin@servetrack.test', '$2b$12$LJ3m4X8o5iJ9Y5Z5Z5Z5ZeXAMPLEHASHREPLACEINPROD0000000000000000000000')
    ON CONFLICT (email) DO NOTHING;
    INSERT INTO profiles (id, nombre_completo) VALUES
        ('00000000-0000-0000-0000-000000000001', 'Super Admin Test')
    ON CONFLICT (id) DO NOTHING;
    INSERT INTO user_roles (user_id, role_id) VALUES
        ('00000000-0000-0000-0000-000000000001', 'super_admin')
    ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_rankings_partidos ON partidos;")
    op.execute("DROP TRIGGER IF EXISTS trg_rankings_sets ON sets_partido;")
    op.execute("DROP FUNCTION IF EXISTS trg_recalc_rankings() CASCADE;")
    op.execute("DROP FUNCTION IF EXISTS trg_recalc_rankings_from_set() CASCADE;")
    op.execute("DROP FUNCTION IF EXISTS fn_recalc_rankings_grupo(UUID) CASCADE;")
    op.execute("DROP FUNCTION IF EXISTS fn_recalc_rankings_general(UUID) CASCADE;")
    op.execute("DROP FUNCTION IF EXISTS is_super_admin() CASCADE;")
    op.execute("DROP FUNCTION IF EXISTS is_organizador(UUID) CASCADE;")
    op.execute("DROP FUNCTION IF EXISTS current_user_id() CASCADE;")
    for tbl in ["reportes_cache","config_global","auditoria","notificaciones","rankings_general","rankings_grupo","estadisticas_atleta","sets_partido","partidos","atletas","equipos","grupos","categorias","ramas","torneos","deportes","user_roles","profiles","roles","users"]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE;")
