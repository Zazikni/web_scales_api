from sqlalchemy import String, Integer, Boolean, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..db import Base


class AutoUpdateSchedule(Base):
    __tablename__ = "auto_update_schedules"
    __table_args__ = (UniqueConstraint("device_id", name="uq_schedule_device"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False
    )

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    last_run_utc: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    device: Mapped["Device"] = relationship("Device", back_populates="schedule")
