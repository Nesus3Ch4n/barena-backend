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

-- Usuarios de prueba (passwords: Atleta123! / Org12345! / Juez12345!)
-- Emails usan dominio barena.app (servetrack.test es rechazado por EmailStr)
INSERT INTO users (id, email, password_hash) VALUES
 ('2df28e6b-10f0-4c3d-867c-7394f84a5b73','atleta@barena.app','$2b$12$8jmv.tPWRBfsUkCXrEjcr.gAef66752kvBnvuJqiLT5c7.rnFhBTe'),
 ('bf1198bb-2906-426c-9e93-f63bc70b154b','organizador@barena.app','$2b$12$l4narC.jeFHJ2JwWZVCJPeVJ/4f2nVHxBSpW2760UZdUodaGPGsxO'),
 ('1abc487e-18ab-4574-a187-07283545f78b','juez@barena.app','$2b$12$QFnRzsC3w/q0PBHneOENOe78o893.aMrORdleKE7tWV.JGlBIVVzu')
ON CONFLICT (email) DO NOTHING;

INSERT INTO profiles (id, nombre_completo)
SELECT id, 'Atleta Test' FROM users WHERE email='atleta@barena.app'
ON CONFLICT (id) DO NOTHING;
INSERT INTO profiles (id, nombre_completo)
SELECT id, 'Organizador Test' FROM users WHERE email='organizador@barena.app'
ON CONFLICT (id) DO NOTHING;
INSERT INTO profiles (id, nombre_completo)
SELECT id, 'Juez Test' FROM users WHERE email='juez@barena.app'
ON CONFLICT (id) DO NOTHING;

INSERT INTO user_roles (user_id, role_id)
SELECT id, 'atleta' FROM users WHERE email='atleta@barena.app'
ON CONFLICT (user_id, role_id) DO NOTHING;
INSERT INTO user_roles (user_id, role_id)
SELECT id, 'organizador' FROM users WHERE email='organizador@barena.app'
ON CONFLICT (user_id, role_id) DO NOTHING;
-- Organizador también es atleta para probar visibilidad combinada
INSERT INTO user_roles (user_id, role_id)
SELECT id, 'atleta' FROM users WHERE email='organizador@barena.app'
ON CONFLICT (user_id, role_id) DO NOTHING;
INSERT INTO user_roles (user_id, role_id)
SELECT id, 'juez_anotador' FROM users WHERE email='juez@barena.app'
ON CONFLICT (user_id, role_id) DO NOTHING;
