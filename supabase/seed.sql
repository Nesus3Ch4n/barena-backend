-- Seed ServeTrack — ejecutar si alembic no crea seed o para reset
INSERT INTO roles (id, descripcion) VALUES
 ('super_admin','Administrador plataforma global'),
 ('organizador','Organizador dueño de torneo'),
 ('juez_anotador','Juez en cancha'),
 ('atleta','Competidor auto-registrado')
ON CONFLICT (id) DO NOTHING;

INSERT INTO deportes (nombre, icono, config_stats) VALUES
 ('volei_playa','volleyball','{"stats":["ATK","BLK","ACE","DIG","REC"],"jugadores_por_equipo":2}'::jsonb)
ON CONFLICT (nombre) DO NOTHING;

INSERT INTO config_global (clave, valor) VALUES
 ('freemium','{"enabled":true}'::jsonb),
 ('realtime_enabled','true'::jsonb)
ON CONFLICT (clave) DO NOTHING;
