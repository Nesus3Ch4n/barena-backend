from sqlalchemy import String, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.database import Base

class ConfigGlobal(Base):
    __tablename__ = "config_global"
    clave: Mapped[str] = mapped_column(String(50), primary_key=True)
    valor: Mapped[dict] = mapped_column(JSON, nullable=False)
    actualizado_en: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
