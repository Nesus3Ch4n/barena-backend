# barena-backend — ServeTrack API (Screaming)

> FastAPI en Vercel (@vercel/python) + Supabase Postgres 19 tablas + JWT propio + triggers rankings

## Estructura screaming

```
app/
  main.py  ← orquesta routers + handlers 400/404/422/500 + CORS + request_id
  shared/
    database.py  (asyncpg)
    errors.py    (AppError, envelope, 8 handlers)
    security.py  (JWT HS256 + bcrypt)
  torneos/ equipos/ atletas/ partidos/ estadisticas/ rankings/ reportes/ auth/ config/
    router.py, schemas.py, service.py, models.py, errors.py
alembic/  ← 001 19 tablas + RLS + triggers
supabase/seed.sql
vercel.json
```

## Local

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # completar DATABASE_URL_SUPABASE
alembic upgrade head  # crea 19 tablas + triggers rankings
uvicorn app.main:app --reload --port 8000  # http://localhost:8000/docs
uvicorn app.main:app --reload --port 8000 --env-file .env
```

## Vercel deploy

1. Import GitHub repo `Nesus3Ch4n/barena-backend` en Vercel → Framework: Other, Root:  `./`
2. Env vars en Vercel Dashboard: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `JWT_SECRET`, `CORS_ORIGINS`
3. Push main → auto deploy → https://barena-backend.vercel.app/health

## DB

- 19 tablas activas (freemium) + 3 futuras billing comentadas
- Triggers rankings: `trg_ranking_after_partido` + `func_recalc_rankings()` (grupos + general V>S>P>DP)
- RLS policies por `torneo.organizador_id = jwt.sub`
- Seed: volei_playa, roles 4, config_global freemium

Ver `alembic/versions/001_initial.py` y `supabase/seed.sql`
