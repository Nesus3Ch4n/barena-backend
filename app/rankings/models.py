import uuid
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.database import Base

class RankingGrupo(Base):
    __tablename__ = "rankings_grupo"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    grupo_id: Mapped[str] = mapped_column(String(36), ForeignKey("grupos.id", ondelete="CASCADE"), nullable=False)
    equipo_id: Mapped[str] = mapped_column(String(36), ForeignKey("equipos.id", ondelete="CASCADE"), nullable=False)
    pj: Mapped[int] = mapped_column(Integer, default=0)
    pg: Mapped[int] = mapped_column(Integer, default=0)
    pp: Mapped[int] = mapped_column(Integer, default=0)
    sets_favor: Mapped[int] = mapped_column(Integer, default=0)
    sets_contra: Mapped[int] = mapped_column(Integer, default=0)
    puntos_favor: Mapped[int] = mapped_column(Integer, default=0)
    puntos_contra: Mapped[int] = mapped_column(Integer, default=0)
    posicion: Mapped[int] = mapped_column(Integer, default=0)

class RankingGeneral(Base):
    __tablename__ = "rankings_general"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    categoria_id: Mapped[str] = mapped_column(String(36), ForeignKey("categorias.id", ondelete="CASCADE"), nullable=False)
    equipo_id: Mapped[str] = mapped_column(String(36), ForeignKey("equipos.id", ondelete="CASCADE"), nullable=False)
    pj: Mapped[int] = mapped_column(Integer, default=0)
    pg: Mapped[int] = mapped_column(Integer, default=0)
    pp: Mapped[int] = mapped_column(Integer, default=0)
    posicion: Mapped[int] = mapped_column(Integer, default=0)
