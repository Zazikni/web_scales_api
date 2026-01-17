from ..db import Base
from sqlalchemy import String, Integer, Boolean, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_device_owner_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    ip: Mapped[str] = mapped_column(String(64), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=1111)
    protocol: Mapped[str] = mapped_column(String(8), nullable=False, default="TCP")

    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    products_cache_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    cached_dirty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    owner: Mapped["User"] = relationship("User", back_populates="devices")
    schedule: Mapped["AutoUpdateSchedule"] = relationship(
        "AutoUpdateSchedule",
        back_populates="device",
        uselist=False,
        cascade="all, delete-orphan",
    )
