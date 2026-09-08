import uuid
from sqlalchemy import String, ForeignKey, DateTime, func, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.database import Base

class ReporteCache(Base):
    __tablename__ = "reportes_cache"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    torneo_id: Mapped[str] = mapped_column(String(36), ForeignKey("torneos.id", ondelete="CASCADE"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=True)
    pdf_url: Mapped[str] = mapped_column(String(500), nullable=True)
    generated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expira_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
