from ..db import Base
from sqlalchemy import String, Integer, Boolean, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    devices: Mapped[list["Device"]] = relationship(
        "Device", back_populates="owner", cascade="all, delete-orphan"
    )
