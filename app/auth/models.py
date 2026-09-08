import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import String, DateTime, func, Table, Column, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.shared.database import Base

# Association M:N user_roles
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", String(30), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("asignado_en", DateTime(timezone=True), server_default=func.now()),
)

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")

class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    nombre_completo: Mapped[str] = mapped_column(String(120), nullable=False)
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=True)
    telefono: Mapped[str] = mapped_column(String(20), nullable=True)
    doc_identidad: Mapped[str] = mapped_column(String(30), nullable=True)
    fecha_nacimiento: Mapped[str] = mapped_column(DateTime, nullable=True)

    user = relationship("User", back_populates="profile")

class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String(30), primary_key=True)  # super_admin, organizador, juez_anotador, atleta
    descripcion: Mapped[str] = mapped_column(String(120), nullable=True)
