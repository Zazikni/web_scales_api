from sqlalchemy import String, Integer, Boolean, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    devices: Mapped[list["Device"]] = relationship("Device", back_populates="owner", cascade="all, delete-orphan")


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_device_owner_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

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
        "AutoUpdateSchedule", back_populates="device", uselist=False, cascade="all, delete-orphan"
    )


class AutoUpdateSchedule(Base):
    __tablename__ = "auto_update_schedules"
    __table_args__ = (UniqueConstraint("device_id", name="uq_schedule_device"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    last_run_utc: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # OK/ERROR
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    device: Mapped["Device"] = relationship("Device", back_populates="schedule")
