import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import String, ForeignKey, Date, func
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.database import Base

class Atleta(Base):
    __tablename__ = "atletas"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    equipo_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("equipos.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    nombre_completo: Mapped[str] = mapped_column(String(120), nullable=False)
    posicion: Mapped[str] = mapped_column(String(20), default="titular", nullable=False)
    foto_url: Mapped[str] = mapped_column(String(500), nullable=True)
    doc_identidad: Mapped[str] = mapped_column(String(30), nullable=True)
    codigo_reclamo: Mapped[str] = mapped_column(String(8), unique=True, nullable=True)
