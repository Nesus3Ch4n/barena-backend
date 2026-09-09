# Deploy Vercel — barena-backend

> Listo para deploy, no se ha desplegado aún. Siguiente paso requiere tu confirmación.

## Estado actual
- Repo: `Nesus3Ch4n/barena-backend` (PRIVATE, `6d5ea20`)
- Local: `D:\proyectos\barena\barena-backend\`
- Runtime: `@vercel/python` (FastAPI 0.110.0, Python 3.14 local, Vercel usa 3.11 — compatible)
- Rutas: 42 endpoints `/api/v1/...` + `/health` + `/docs`
- DB: 19 tablas + triggers `001_initial_19_tables.py` (requiere `DATABASE_URL` Supabase para `alembic upgrade head`)

## Archivos clave verificados
- `vercel.json:1` → `{"builds":[{"src":"app/main.py","use":"@vercel/python"}],"routes":[{"src":"/(.*)","dest":"app/main.py"}]}` ✔
- `requirements.txt:1` → 15 deps, sin `uvicorn` necesario en Vercel (usa su server), pero se deja para local ✔
- `app/main.py:1` → `app` expuesto para Vercel ✔
- `.env.example:1` → template env ✔
- `app/shared/errors.py:1` → envelope + request_id ✔

## Env vars requeridas en Vercel Dashboard
Configurar en `vercel.com → barena-backend → Settings → Environment Variables` (Production + Preview + Development):

```
DATABASE_URL=postgresql+psycopg://postgres.proyecto:password@aws-1-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require
DATABASE_URL_SYNC=postgresql://postgres.proyecto:password@aws-0-us-east-1.pooler.supabase.com:6543/postgres
SUPABASE_URL=https://proyecto.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
JWT_SECRET=<32+ chars, openssl rand -hex 32>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=15
JWT_REFRESH_DAYS=7
CORS_ORIGINS=https://barena-frontend.vercel.app,http://localhost:3000
FREEMIUM=true
REALTIME_ENABLED=true
```

> Si aún no tienes Supabase, puedes deployar igual y `/health` responderá, pero `/torneos` fallará hasta setear `DATABASE_URL`. Recomendado crear Supabase antes.

## Pasos para deploy (cuando confirmes)

### Opción A — Via Vercel Dashboard (recomendada, 1 click)
1. `vercel.com/new` → Import `Nesus3Ch4n/barena-backend`
2. Framework: `Other` (detecta Python), Root: `./`
3. Add Env Vars (las de arriba)
4. Deploy → URL: `https://barena-backend.vercel.app` (ejemplo)
5. Test: `curl https://barena-backend.vercel.app/health`

### Opción B — Via CLI (yo lo hago si confirmas)
```bash
cd D:\proyectos\barena\barena-backend
npx vercel --prod  # linka y deploya
# o: npx vercel --prod --yes
```

### Post-deploy
- `alembic upgrade head` → ejecutar local con `DATABASE_URL_SYNC` seteado para crear tablas en Supabase
- `curl https://<url>/docs` → Swagger con 42 endpoints
- `curl https://<url>/api/v1/auth/register -X POST ...` → test

## Limit 10s Hobby
Todos los endpoints actuales <3s excepto `POST /bulk` (si >20 equipos → usa `202` + BackgroundTasks). Hobby 10s OK para MVP.

## Checklist pre-deploy (yo ya verifiqué)
- [x] `app/main.py` importa OK (42 rutas)
- [x] `vercel.json` válido
- [x] `requirements.txt` sin conflictos
- [x] `.env.example` documentado
- [ ] `DATABASE_URL` Supabase creado (pendiente tú)
- [ ] Confirmación tuya para deploy

## Siguiente
Responde `deploy` y ejecuto `npx vercel --prod` desde `D:\proyectos\barena\barena-backend\`. Si prefieres Dashboard, dímelo y te paso el link directo.
