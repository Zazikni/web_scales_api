import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..models import AutoUpdateSchedule
from .auto_update_service import auto_update_job

logger = logging.getLogger("app.scheduler")


scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)


def scheduler_start() -> None:
    if not settings.scheduler_service_enabled:
        logger.info("scheduler disabled | skip start")
        return

    if not scheduler.running:
        scheduler.start()
        logger.info("scheduler started")


def scheduler_shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler stopped")


def scheduler_rebuild_jobs_from_db() -> None:
    """
    Пересоздать jobs из таблицы расписаний.
    """
    if not settings.scheduler_enabled:
        logger.info("scheduler disabled | skip rebuild_jobs_from_db")
        return

    db: Session = SessionLocal()
    try:
        schedules = db.query(AutoUpdateSchedule).all()
        for sch in schedules:
            job_id = f"auto_update:{sch.device_id}"

            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)

            if sch.enabled:
                scheduler.add_job(
                    auto_update_job,
                    "interval",
                    minutes=sch.interval_minutes,
                    args=[sch.device_id],
                    id=job_id,
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                )

        logger.info("scheduler jobs rebuilt | count=%d", len(schedules))
    finally:
        db.close()
