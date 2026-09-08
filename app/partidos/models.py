import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.database import Base

class Partido(Base):
    __tablename__ = "partidos"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    categoria_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("categorias.id", ondelete="CASCADE"), nullable=False)
    grupo_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("grupos.id", ondelete="SET NULL"), nullable=True)
    fase: Mapped[str] = mapped_column(String(20), default="grupos", nullable=False)
    equipo_local_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("equipos.id"), nullable=False)
    equipo_visit_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("equipos.id"), nullable=False)
    cancha: Mapped[str] = mapped_column(String(50), nullable=True)
    fecha_hora: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente", nullable=False)
    ganador_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("equipos.id"), nullable=True)
    es_cuadro_perdedores: Mapped[bool] = mapped_column(Boolean, default=False)
    arbitro_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

class SetPartido(Base):
    __tablename__ = "sets_partido"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    partido_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("partidos.id", ondelete="CASCADE"), nullable=False)
    numero_set: Mapped[int] = mapped_column(Integer, nullable=False)
    pts_local: Mapped[int] = mapped_column(Integer, nullable=False)
    pts_visitante: Mapped[int] = mapped_column(Integer, nullable=False)
    ganador_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("equipos.id"), nullable=True)
    duracion_min: Mapped[int] = mapped_column(Integer, nullable=True)
