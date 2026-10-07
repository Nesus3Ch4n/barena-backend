import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.database import Base


class PQR(Base):
    __tablename__ = "pqr"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    torneo_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("torneos.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tipo: Mapped[str] = mapped_column(String(20), default="peticion", nullable=False)
    asunto: Mapped[str] = mapped_column(String(120), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="abierta", nullable=False)
    respuesta: Mapped[str] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
