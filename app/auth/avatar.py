"""Carga persistente de avatares usando Supabase Storage.

No guarda base64 en PostgreSQL. Requiere SUPABASE_URL y una service key. Si el
bucket público `avatars` no existe, intenta crearlo; si el almacenamiento no
está configurado responde 503 y el perfil conserva su imagen anterior.
"""
from __future__ import annotations

import os

import httpx
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_profile
from app.shared.errors import AppError

MAX_BYTES = 3 * 1024 * 1024
TIPOS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


async def guardar_avatar(db: AsyncSession, user_id: str, archivo: UploadFile) -> str:
    content_type = (archivo.content_type or "").split(";")[0].strip().lower()
    extension = TIPOS.get(content_type)
    if not extension:
        raise AppError(400, "IMAGEN_INVALIDA", "La fotografía debe ser JPG, PNG o WEBP")

    contenido = await archivo.read()
    if not contenido:
        raise AppError(400, "IMAGEN_VACIA", "La fotografía está vacía")
    if len(contenido) > MAX_BYTES:
        raise AppError(413, "IMAGEN_DEMASIADO_GRANDE", "La fotografía supera el límite de 3 MB")

    supabase_url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        raise AppError(503, "STORAGE_NOT_CONFIGURED", "El almacenamiento de imágenes no está configurado")

    headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}
    objeto = f"{user_id}.{extension}"
    async with httpx.AsyncClient(timeout=30) as client:
        # 400/409 = el bucket ya existe. No se considera un error.
        await client.post(
            f"{supabase_url}/storage/v1/bucket",
            headers=headers,
            json={
                "id": "avatars",
                "name": "avatars",
                "public": True,
                "file_size_limit": MAX_BYTES,
                "allowed_mime_types": list(TIPOS),
            },
        )
        res = await client.put(
            f"{supabase_url}/storage/v1/object/avatars/{objeto}",
            headers={**headers, "Content-Type": content_type, "x-upsert": "true"},
            content=contenido,
        )
        if res.status_code >= 300:
            raise AppError(502, "STORAGE_UPLOAD_FAILED", "No pudimos subir la fotografía al almacenamiento")

    url = f"{supabase_url}/storage/v1/object/public/avatars/{objeto}"
    profile = await get_profile(db, user_id)
    if not profile:
        raise AppError(404, "PROFILE_NOT_FOUND", "Perfil no encontrado")
    profile.avatar_url = url
    await db.flush()
    return url
