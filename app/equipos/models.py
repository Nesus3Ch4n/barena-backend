import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import String, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.database import Base

class Equipo(Base):
    __tablename__ = "equipos"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    categoria_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("categorias.id", ondelete="CASCADE"), nullable=False)
    grupo_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("grupos.id", ondelete="SET NULL"), nullable=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    ciudad: Mapped[str] = mapped_column(String(80), nullable=True)
    foto_url: Mapped[str] = mapped_column(String(500), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente", nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=True)
    inscrito_en: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
