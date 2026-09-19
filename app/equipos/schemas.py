from pydantic import BaseModel, Field
from typing import List, Optional

class AtletaIn(BaseModel):
    nombre_completo: str = Field(min_length=2, max_length=120)
    posicion: str = Field(default="titular", pattern="^(titular|libero)$")
    doc_identidad: Optional[str] = None
    fecha_nacimiento: Optional[str] = None

class EquipoCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    ciudad: Optional[str] = None
    categoria_id: str = Field(min_length=36)
    atletas: List[AtletaIn] = Field(min_length=2, max_length=3)
    foto_url: Optional[str] = None

class EquipoAprobarIn(BaseModel):
    grupo_id: Optional[str] = None
    seed: Optional[int] = Field(default=None, ge=1)

class EquipoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=80)
    ciudad: Optional[str] = None
    categoria_id: Optional[str] = None
    atletas: Optional[List[AtletaIn]] = None
    foto_url: Optional[str] = None
    grupo_id: Optional[str] = None
    seed: Optional[int] = Field(None, ge=1)
    forzar: Optional[bool] = False

class ReemplazoIn(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=80)
    ciudad: Optional[str] = None
    atletas: List[AtletaIn] = Field(min_length=2, max_length=3)
    modo: Optional[str] = Field(None, pattern="^(conservar_historial|nueva_participacion)$")

class EquipoOut(BaseModel):
    id: str
    nombre: str
    categoria_id: str
    grupo_id: Optional[str]
    estado: str
    seed: Optional[int]
