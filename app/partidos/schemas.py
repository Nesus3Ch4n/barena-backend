from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class GenerarFixtureIn(BaseModel):
    crear_grupos: bool = True
    # opcional: semilla para shuffle

class ProgramarIn(BaseModel):
    cancha: Optional[str] = None
    fecha_hora: Optional[datetime] = None

class SetIn(BaseModel):
    numero_set: int = Field(ge=1, le=5)
    pts_local: int = Field(ge=0)
    pts_visitante: int = Field(ge=0)
    duracion_min: Optional[int] = None

class ResultadoIn(BaseModel):
    sets: List[SetIn] = Field(min_length=1, max_length=5)
    # ganador se calcula

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
