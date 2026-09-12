import uuid
from sqlalchemy import String, Date, Boolean, Integer, Text, ForeignKey, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.shared.database import Base

class Deporte(Base):
    __tablename__ = "deportes"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    icono: Mapped[str] = mapped_column(String(30), nullable=True)
    config_stats: Mapped[dict] = mapped_column(JSON, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

class Torneo(Base):
    __tablename__ = "torneos"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    deporte_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("deportes.id"), nullable=False)
    organizador_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    fecha_inicio: Mapped[str] = mapped_column(Date, nullable=True)
    fecha_fin: Mapped[str] = mapped_column(Date, nullable=True)
    sede: Mapped[str] = mapped_column(String(120), nullable=True)
    ciudad: Mapped[str] = mapped_column(String(80), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="borrador", nullable=False)
    publico: Mapped[bool] = mapped_column(Boolean, default=False)
    config_visibilidad: Mapped[dict] = mapped_column(JSON, default=lambda: {"fixture_visible": False, "grupos_visible": False, "posiciones_visible": False, "stats_visible": True, "ranking_visible": False})
    creado_en: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Rama(Base):
    __tablename__ = "ramas"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    torneo_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("torneos.id", ondelete="CASCADE"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    nombre_custom: Mapped[str] = mapped_column(String(50), nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

class Categoria(Base):
    __tablename__ = "categorias"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    rama_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("ramas.id", ondelete="CASCADE"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(50), nullable=False)
    formato: Mapped[str] = mapped_column(String(20), default="grupos")
    cuadro_perdedores: Mapped[bool] = mapped_column(Boolean, default=False)
    equipos_x_grupo: Mapped[int] = mapped_column(Integer, default=4)
    sets_x_partido: Mapped[int] = mapped_column(Integer, default=3)
    puntos_x_set: Mapped[int] = mapped_column(Integer, default=21)
    avance_x_grupo: Mapped[int] = mapped_column(Integer, default=2)
    criterio_clasif: Mapped[str] = mapped_column(String(200), default="PG>SF>PF>DP")
    ranking_general_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    bracket_tipo: Mapped[str] = mapped_column(String(20), default="general")

class Grupo(Base):
    __tablename__ = "grupos"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    categoria_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("categorias.id", ondelete="CASCADE"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(10), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, default=1)
