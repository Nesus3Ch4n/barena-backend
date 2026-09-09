from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Any
from datetime import date

class CategoriaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=50)
    formato: str = Field(default="grupos", pattern="^(grupos|eliminatoria|round_robin|custom)$")
    cuadro_perdedores: bool = False
    equipos_x_grupo: int = Field(default=4, ge=2, le=8)
    sets_x_partido: int = Field(default=3)
    puntos_x_set: int = Field(default=21)
    avance_x_grupo: int = Field(default=2, ge=1, le=4)
    criterio_clasif: str = "V>S>P>DP"

    @field_validator("sets_x_partido")
    @classmethod
    def check_sets(cls, v):
        if v not in (1, 3, 5):
            raise ValueError("sets_x_partido debe ser 1, 3 o 5")
        return v

    @field_validator("puntos_x_set")
    @classmethod
    def check_puntos(cls, v):
        if v not in (15, 21, 25):
            raise ValueError("puntos_x_set debe ser 15, 21 o 25")
        return v

    class Config:
        extra = "forbid"

class RamaIn(BaseModel):
    tipo: str = Field(pattern="^(masc|fem|mixto)$")
    nombre_custom: Optional[str] = None
    activa: bool = True
    categorias: List[CategoriaIn] = Field(default_factory=list)

class TorneoCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    deporte_id: Optional[str] = None
    deporte_nombre: Optional[str] = "volei_playa"
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    sede: Optional[str] = None
    ciudad: Optional[str] = None
    publico: bool = False
    ramas: List[RamaIn] = Field(default_factory=list)

    @field_validator("deporte_nombre")
    @classmethod
    def normalize_deporte(cls, v):
        return v.lower().strip() if v else v

class VisibilidadUpdate(BaseModel):
    fixture_visible: Optional[bool] = None
    grupos_visible: Optional[bool] = None
    posiciones_visible: Optional[bool] = None
    stats_visible: Optional[bool] = None
    ranking_visible: Optional[bool] = None
    publico: Optional[bool] = None

class TorneoOut(BaseModel):
    id: str
    nombre: str
    slug: str
    deporte_id: str
    organizador_id: str
    fecha_inicio: Optional[date]
    fecha_fin: Optional[date]
    sede: Optional[str]
    ciudad: Optional[str]
    estado: str
    publico: bool
    config_visibilidad: Any

class RamaOut(BaseModel):
    id: str
    torneo_id: str
    tipo: str
    nombre_custom: Optional[str]
    activa: bool

class CategoriaOut(BaseModel):
    id: str
    rama_id: str
    nombre: str
    formato: str
    cuadro_perdedores: bool
    equipos_x_grupo: int
    sets_x_partido: int
    puntos_x_set: int
    avance_x_grupo: int
