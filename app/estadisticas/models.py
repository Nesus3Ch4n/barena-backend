import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.database import Base

class EstadisticaAtleta(Base):
    __tablename__ = "estadisticas_atleta"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    atleta_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("atletas.id", ondelete="CASCADE"), nullable=False)
    partido_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("partidos.id", ondelete="CASCADE"), nullable=False)
    ataques_pts: Mapped[int] = mapped_column(Integer, default=0)
    bloqueos_pts: Mapped[int] = mapped_column(Integer, default=0)
    saques_directos: Mapped[int] = mapped_column(Integer, default=0)
    errores_propios: Mapped[int] = mapped_column(Integer, default=0)
    defensas_dig: Mapped[int] = mapped_column(Integer, default=0)
    recepciones_perf: Mapped[int] = mapped_column(Integer, default=0)
    ataques_total: Mapped[int] = mapped_column(Integer, default=0)
    saques_total: Mapped[int] = mapped_column(Integer, default=0)
