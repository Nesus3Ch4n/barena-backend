import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import String, Boolean, ForeignKey, DateTime, func, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.database import Base


class Notificacion(Base):
    __tablename__ = "notificaciones"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(30), default="general", nullable=False)
    titulo: Mapped[str] = mapped_column(String(120), nullable=False)
    cuerpo: Mapped[str] = mapped_column(Text, nullable=True)
    partido_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("partidos.id", ondelete="CASCADE"), nullable=True)
    leida: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    creada_en = mapped_column(DateTime(timezone=True), server_default=func.now())
