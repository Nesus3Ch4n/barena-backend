from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime

class GenerarFixtureIn(BaseModel):
    crear_grupos: bool = True
    bracket_tipo: Optional[str] = Field(default=None, pattern="^(general|diamante|oro|diamante_oro)$")

class ProgramarIn(BaseModel):
    cancha: Optional[str] = Field(None, max_length=50)
    fecha_hora: Optional[datetime] = None

class SetIn(BaseModel):
    numero_set: int = Field(ge=1, le=5)
    pts_local: int = Field(ge=0, le=99)
    pts_visitante: int = Field(ge=0, le=99)
    duracion_min: Optional[int] = Field(None, ge=1, le=120)

    @field_validator("pts_local", "pts_visitante")
    @classmethod
    def check_no_empate_at_level(cls, v):
        return v

class ResultadoIn(BaseModel):
    sets: List[SetIn] = Field(min_length=1, max_length=5)

class PartidoOut(BaseModel):
    id: str
    categoria_id: str
    grupo_id: Optional[str]
    fase: str
    equipo_local_id: str
    equipo_visit_id: str
    cancha: Optional[str]
    fecha_hora: Optional[datetime]
    estado: str
    ganador_id: Optional[str]
    bracket_tipo: str = "general"

class PartidoCreate(BaseModel):
    categoria_id: str
    grupo_id: Optional[str] = None
    fase: str = Field(default="grupos", pattern="^(grupos|cuartos|semi|final|tercer_puesto|octavos|ronda)$")
    equipo_local_id: str
    equipo_visit_id: str
    cancha: Optional[str] = Field(None, max_length=50)
    fecha_hora: Optional[datetime] = None
    bracket_tipo: str = Field(default="general", pattern="^(general|diamante|oro)$")

class PartidoUpdate(BaseModel):
    grupo_id: Optional[str] = None
    fase: Optional[str] = Field(default=None, pattern="^(grupos|cuartos|semi|final|tercer_puesto|octavos|ronda)$")
    equipo_local_id: Optional[str] = None
    equipo_visit_id: Optional[str] = None
    cancha: Optional[str] = Field(None, max_length=50)
    fecha_hora: Optional[datetime] = None
    bracket_tipo: Optional[str] = Field(default=None, pattern="^(general|diamante|oro)$")
