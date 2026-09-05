"""
ServeTrack — Sistema de errores robusto (screaming: shared/errors)
Envelope único + handlers 400/401/403/404/422/500 + request_id
"""
import uuid
import logging
from typing import Any, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("servetrack.errors")

# ---------- Base ----------
class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Optional[dict] = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)

# 400
class BadRequest(AppError):
    def __init__(self, code="BAD_REQUEST", message="Solicitud inválida", details=None):
        super().__init__(400, code, message, details)

# 401
class Unauthorized(AppError):
    def __init__(self, message="No autenticado", details=None):
        super().__init__(401, "UNAUTHORIZED", message, details)

# 403
class Forbidden(AppError):
    def __init__(self, message="No autorizado", details=None):
        super().__init__(403, "FORBIDDEN", message, details)

# 404
class NotFound(AppError):
    def __init__(self, code="NOT_FOUND", message="Recurso no encontrado", details=None):
        super().__init__(404, code, message, details)

class TorneoNotFound(NotFound):
    def __init__(self, torneo_id):
        super().__init__("TORNEO_NOT_FOUND", f"Torneo {torneo_id} no existe", {"id": str(torneo_id)})

class PartidoNotFound(NotFound):
    def __init__(self, partido_id):
        super().__init__("PARTIDO_NOT_FOUND", f"Partido {partido_id} no existe", {"id": str(partido_id)})

class EquipoNotFound(NotFound):
    def __init__(self, equipo_id):
        super().__init__("EQUIPO_NOT_FOUND", f"Equipo {equipo_id} no existe", {"id": str(equipo_id)})

# ---------- Handlers ----------
def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req_unknown")

async def app_error_handler(request: Request, exc: AppError):
    rid = _request_id(request)
    logger.warning(f"[{rid}] AppError {exc.code}: {exc.message} details={exc.details}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "error": {"code": exc.code, "message": exc.message, "details": exc.details, "request_id": rid},
        },
        headers={"X-Request-ID": rid},
    )

async def validation_error_handler(request: Request, exc: RequestValidationError):
    rid = _request_id(request)
    details = {"errors": exc.errors()}
    logger.warning(f"[{rid}] Validation 422: {details}")
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "data": None,
            "error": {"code": "VALIDATION_ERROR", "message": "Error de validación", "details": details, "request_id": rid},
        },
        headers={"X-Request-ID": rid},
    )

async def unhandled_error_handler(request: Request, exc: Exception):
    rid = _request_id(request)
    logger.error(f"[{rid}] Unhandled 500: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "error": {"code": "INTERNAL_ERROR", "message": "Error interno del servidor", "details": {}, "request_id": rid},
        },
        headers={"X-Request-ID": rid},
    )

# ---------- Middleware request_id ----------
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
