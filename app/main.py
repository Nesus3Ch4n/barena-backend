"""
ServeTrack API — FastAPI en Vercel (@vercel/python)
Screaming: main solo orquesta routers + errores
"""
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from app.shared.errors import (
    AppError, app_error_handler, validation_error_handler, unhandled_error_handler, RequestIDMiddleware
)

# Routers screaming
from app.auth.router import router as auth_router
from app.torneos.router import router as torneos_router, public_router as public_router
from app.equipos.router import router as equipos_router, equipo_router as equipo_op_router
from app.atletas.router import router as atletas_router
from app.partidos.router import router as partidos_router, torneo_partidos_router, categoria_fixture_router
from app.estadisticas.router import router as estadisticas_router, atleta_router as estadisticas_atleta_router
from app.rankings.router import router as rankings_router, categoria_router as rankings_categoria_router, torneo_router as rankings_torneo_router
from app.reportes.router import router as reportes_router
from app.config.router import router as config_router

app = FastAPI(
    title="ServeTrack API",
    version="3.0.0",
    description="SaaS Torneos Volei Playa — Screaming + Vercel + Supabase + JWT propio",
)

# Middleware
app.add_middleware(RequestIDMiddleware)
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,https://*.vercel.app").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

# Exception handlers (400, 404, 422, 500)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

# Routers /api/v1
for r in [auth_router, torneos_router, equipos_router, atletas_router, partidos_router, estadisticas_router, rankings_router, reportes_router, config_router]:
    app.include_router(r, prefix="/api/v1")
app.include_router(equipo_op_router, prefix="/api/v1")
app.include_router(public_router, prefix="/api/v1")
app.include_router(torneo_partidos_router, prefix="/api/v1")
app.include_router(categoria_fixture_router, prefix="/api/v1")
app.include_router(estadisticas_atleta_router, prefix="/api/v1")
app.include_router(rankings_categoria_router, prefix="/api/v1")
app.include_router(rankings_torneo_router, prefix="/api/v1")

@app.get("/health")
async def health(request: Request):
    return {"success": True, "data": {"status": "ok", "version": "3.0.0", "freemium": True}, "error": None}

@app.get("/")
async def root():
    return {"success": True, "data": {"message": "ServeTrack API — Vercel + Supabase", "docs": "/docs"}, "error": None}

# Para Vercel: export app
# vercel.json -> "src": "app/main.py"
