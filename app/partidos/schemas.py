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
    tarjetas_amarillas_local: int = Field(default=0, ge=0, le=99)
    tarjetas_rojas_local: int = Field(default=0, ge=0, le=99)
    tarjetas_amarillas_visit: int = Field(default=0, ge=0, le=99)
    tarjetas_rojas_visit: int = Field(default=0, ge=0, le=99)

class LiveEventoIn(BaseModel):
    """Acción del juez en el marcador en vivo.
    tipo: inicio|punto|set_ganado|tiempo_muerto|tiempo_receso|tiempo_medico|
          tarjeta_amarilla|tarjeta_roja|saque|orden_saque|cambio_lado|individual
    lado: 'local' | 'visitante' (opcional, no aplica a inicio/cambio_lado)
    atleta_id: para saque, orden_saque (en extra.orden) e individual
    razon: 'demora' | 'conducta' (tarjetas)
    extra.tipo: 'saque_directo'|'defensa'|'ataque'|'bloqueo' (individual)
    extra.orden: lista de atleta_ids (orden_saque)"""
    tipo: str = Field(pattern="^(inicio|punto|set_ganado|tiempo_muerto|tiempo_receso|tiempo_medico|tarjeta_amarilla|tarjeta_roja|saque|orden_saque|cambio_lado|individual)$")
    lado: Optional[str] = Field(default=None, pattern="^(local|visitante)$")
    atleta_id: Optional[str] = None
    razon: Optional[str] = Field(default=None, pattern="^(demora|conducta)$")
    numero: Optional[int] = Field(default=None, ge=1, le=99)
    extra: Optional[dict] = None

class PartidoOut(BaseModel):
    id: str
    categoria_id: str
    grupo_id: Optional[str]
    fase: str
    llave: int = 0
    equipo_local_id: Optional[str]
    equipo_visit_id: Optional[str]
    cancha: Optional[str]
    fecha_hora: Optional[datetime]
    estado: str
    ganador_id: Optional[str]
    bracket_tipo: str = "general"
    sets: List[dict] = Field(default_factory=list)

class PartidoCreate(BaseModel):
    categoria_id: str
    grupo_id: Optional[str] = None
    fase: str = Field(default="grupos", pattern="^(grupos|treintaidosavos|dieciseisavos|octavos|cuartos|semi|final|tercer_puesto|ronda)$")
    llave: int = 0
    equipo_local_id: str
    equipo_visit_id: str
    cancha: Optional[str] = Field(None, max_length=50)
    fecha_hora: Optional[datetime] = None
    bracket_tipo: str = Field(default="general", pattern="^(general|diamante|oro)$")

class PartidoUpdate(BaseModel):
    grupo_id: Optional[str] = None
    fase: Optional[str] = Field(default=None, pattern="^(grupos|treintaidosavos|dieciseisavos|octavos|cuartos|semi|final|tercer_puesto|ronda)$")
    llave: Optional[int] = None
    equipo_local_id: Optional[str] = None
    equipo_visit_id: Optional[str] = None
    cancha: Optional[str] = Field(None, max_length=50)
    fecha_hora: Optional[datetime] = None
    bracket_tipo: Optional[str] = Field(default=None, pattern="^(general|diamante|oro)$")
