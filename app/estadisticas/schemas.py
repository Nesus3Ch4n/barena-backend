from pydantic import BaseModel, Field
from typing import Optional

class EstadisticaIn(BaseModel):
    atleta_id: str
    ataques_pts: int = Field(default=0, ge=0)
    bloqueos_pts: int = Field(default=0, ge=0)
    saques_directos: int = Field(default=0, ge=0)
    errores_propios: int = Field(default=0, ge=0)
    defensas_dig: int = Field(default=0, ge=0)
    recepciones_perf: int = Field(default=0, ge=0)
    ataques_total: int = Field(default=0, ge=0)
    saques_total: int = Field(default=0, ge=0)

class EstadisticaOut(BaseModel):
    atleta_id: str
    partido_id: str
    puntos_total: int
    ataques_pts: int
    bloqueos_pts: int
    saques_directos: int
    errores_propios: int
    defensas_dig: int
    eft_ataque: Optional[float] = None
    eft_saque: Optional[float] = None
