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
    criterio_clasif: str = Field(default="PG>SF>PF>DP", max_length=200)
    ranking_general_enabled: bool = True
    bracket_tipo: str = Field(default="general", pattern="^(general|diamante|oro|diamante_oro)$")

    @field_validator("sets_x_partido")
    @classmethod
    def check_sets(cls, v):
        if v not in (1, 2, 3, 5):
            raise ValueError("sets_x_partido debe ser 1, 2, 3 o 5")
        return v

    @field_validator("puntos_x_set")
    @classmethod
    def check_puntos(cls, v):
        if v not in (15, 21, 25):
            raise ValueError("puntos_x_set debe ser 15, 21 o 25")
        return v

    @field_validator("criterio_clasif")
    @classmethod
    def check_criterio(cls, v):
        # permite 1-16 criterios separados por >  (ej: PG>SF>PF>DP>PTS)
        if v is None:
            return v
        parts = [p.strip() for p in v.split(">") if p.strip()]
        if len(parts) < 1 or len(parts) > 16:
            raise ValueError("criterio_clasif debe tener 1-16 criterios separados por >")
        valid = {"PG","PE","PP","PJ","PTS","SF","SC","PF","PC","DP","DS","V","S","P","SG","PPG"}
        # mapea V->PG, S->SF, P->PF para compatibilidad
        for p in parts:
            if p not in valid and p.upper() not in valid:
                # permitir tambien formas antiguas V,S,P
                if p not in {"V","S","P","DP","SG"}:
                    raise ValueError(f"criterio desconocido: {p}")
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

class TorneoUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=120)
    sede: Optional[str] = Field(default=None, max_length=120)
    ciudad: Optional[str] = Field(default=None, max_length=120)
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    publico: Optional[bool] = None
    deporte_nombre: Optional[str] = Field(default=None, max_length=50)

class RamaUpdate(BaseModel):
    tipo: Optional[str] = Field(default=None, pattern="^(masc|fem|mixto)$")
    nombre_custom: Optional[str] = Field(default=None, max_length=50)
    activa: Optional[bool] = None

class CategoriaUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=50)
    formato: Optional[str] = Field(default=None, pattern="^(grupos|eliminatoria|round_robin|custom)$")
    cuadro_perdedores: Optional[bool] = None
    equipos_x_grupo: Optional[int] = Field(default=None, ge=2, le=8)
    sets_x_partido: Optional[int] = None
    puntos_x_set: Optional[int] = None
    avance_x_grupo: Optional[int] = Field(default=None, ge=1, le=4)
    criterio_clasif: Optional[str] = None
    ranking_general_enabled: Optional[bool] = None
    bracket_tipo: Optional[str] = Field(default=None, pattern="^(general|diamante|oro|diamante_oro)$")

    @field_validator("sets_x_partido")
    @classmethod
    def check_sets_upd(cls, v):
        if v is None:
            return v
        if v not in (1, 2, 3, 5):
            raise ValueError("sets_x_partido debe ser 1, 2, 3 o 5")
        return v

    @field_validator("puntos_x_set")
    @classmethod
    def check_puntos_upd(cls, v):
        if v is None:
            return v
        if v not in (15, 21, 25):
            raise ValueError("puntos_x_set debe ser 15, 21 o 25")
        return v

    @field_validator("criterio_clasif")
    @classmethod
    def check_criterio_upd(cls, v):
        if v is None:
            return v
        parts = [p.strip() for p in v.split(">") if p.strip()]
        if len(parts) < 1 or len(parts) > 16:
            raise ValueError("criterio_clasif debe tener 1-16 criterios")
        return v

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
    ranking_general_enabled: bool
    bracket_tipo: str
