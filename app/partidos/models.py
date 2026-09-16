import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.database import Base

class Partido(Base):
    __tablename__ = "partidos"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    categoria_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("categorias.id", ondelete="CASCADE"), nullable=False)
    grupo_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("grupos.id", ondelete="SET NULL"), nullable=True)
    fase: Mapped[str] = mapped_column(String(20), default="grupos", nullable=False)
    llave: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    equipo_local_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("equipos.id"), nullable=True)
    equipo_visit_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("equipos.id"), nullable=True)
    cancha: Mapped[str] = mapped_column(String(50), nullable=True)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente", nullable=False)
    ganador_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("equipos.id"), nullable=True)
    es_cuadro_perdedores: Mapped[bool] = mapped_column(Boolean, default=False)
    bracket_tipo: Mapped[str] = mapped_column(String(20), default="general")
    orden_en_round: Mapped[int] = mapped_column(Integer, nullable=True)
    partido_siguiente_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("partidos.id", ondelete="SET NULL"), nullable=True)
    arbitro_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tarjetas_amarillas_local: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tarjetas_rojas_local: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tarjetas_amarillas_visit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tarjetas_rojas_visit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

class SetPartido(Base):
    __tablename__ = "sets_partido"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    partido_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("partidos.id", ondelete="CASCADE"), nullable=False)
    numero_set: Mapped[int] = mapped_column(Integer, nullable=False)
    pts_local: Mapped[int] = mapped_column(Integer, nullable=False)
    pts_visitante: Mapped[int] = mapped_column(Integer, nullable=False)
    ganador_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("equipos.id"), nullable=True)
    duracion_min: Mapped[int] = mapped_column(Integer, nullable=True)

class PartidoEvento(Base):
    """Bitácora del marcador en vivo. Cada acción del juez (punto, set, tiempo,
    tarjeta, saque, orden de saque, cambio de lado, acción individual) se guarda
    aquí; el estado se deriva del log y 'revocado' permite deshacer sin borrar."""
    __tablename__ = "partido_eventos"
    __table_args__ = (Index("ix_partido_eventos_partido_seq", "partido_id", "seq"),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    partido_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("partidos.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String(24), nullable=False)
    lado: Mapped[str] = mapped_column(String(10), nullable=True)
    atleta_id: Mapped[str] = mapped_column(String(36), nullable=True)
    razon: Mapped[str] = mapped_column(String(24), nullable=True)
    numero: Mapped[int] = mapped_column(Integer, nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, nullable=True)
    revocado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    creado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
