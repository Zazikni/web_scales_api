import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.services.scheduler_service import scheduler_rebuild_jobs_from_db
from app.config import settings
from app.db import get_db
from app.deps import get_current_user, get_user_device_or_404
from app.models import User, AutoUpdateSchedule
from app.schemas import AutoUpdateConfig

logger = logging.getLogger("app.main")

router = APIRouter(prefix="/devices", tags=["auto_update"])


@router.get("/{device_id}/auto-update", response_model=AutoUpdateConfig)
def get_auto_update(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "get auto-update requested | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    dev = get_user_device_or_404(db, user.id, device_id)
    sch = (
        db.query(AutoUpdateSchedule)
        .filter(AutoUpdateSchedule.device_id == dev.id)
        .one_or_none()
    )
    if not sch:
        logger.info(
            "auto-update config missing | user_id=%s | device_id=%s | action=create_default",
            user.id,
            dev.id,
        )
        sch = AutoUpdateSchedule(
            device_id=dev.id,
            enabled=False,
            interval_minutes=settings.scheduler_interval,
            last_run_utc=None,
            last_status=None,
            last_error=None,
        )
        db.add(sch)
        db.commit()
        db.refresh(sch)
    logger.info(
        "get auto-update success | user_id=%s | device_id=%s | enabled=%s | interval_minutes=%s",
        user.id,
        dev.id,
        sch.enabled,
        sch.interval_minutes,
    )
    return AutoUpdateConfig(
        enabled=sch.enabled,
        interval_minutes=sch.interval_minutes,
        last_run_utc=sch.last_run_utc,
        last_status=sch.last_status,
        last_error=sch.last_error,
    )


@router.put("/{device_id}/auto-update", response_model=AutoUpdateConfig)
def set_auto_update(
    device_id: int,
    req: AutoUpdateConfig,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "set auto-update requested | user_id=%s | device_id=%s | enabled=%s | interval_minutes=%s",
        user.id,
        device_id,
        req.enabled,
        req.interval_minutes,
    )
    dev = get_user_device_or_404(db, user.id, device_id)

    sch = (
        db.query(AutoUpdateSchedule)
        .filter(AutoUpdateSchedule.device_id == dev.id)
        .one_or_none()
    )
    if not sch:
        logger.info(
            "auto-update config missing | user_id=%s | device_id=%s | action=create",
            user.id,
            dev.id,
        )
        sch = AutoUpdateSchedule(
            device_id=dev.id,
            enabled=req.enabled,
            interval_minutes=req.interval_minutes,
            last_run_utc=None,
            last_status=None,
            last_error=None,
        )
    else:
        logger.info(
            "auto-update config found | user_id=%s | device_id=%s | action=update",
            user.id,
            dev.id,
        )
        sch.enabled = req.enabled
        sch.interval_minutes = req.interval_minutes

    db.add(sch)
    db.commit()
    db.refresh(sch)

    scheduler_rebuild_jobs_from_db()
    logger.info(
        "set auto-update success | user_id=%s | device_id=%s | enabled=%s | interval_minutes=%s",
        user.id,
        dev.id,
        sch.enabled,
        sch.interval_minutes,
    )

    return AutoUpdateConfig(
        enabled=sch.enabled,
        interval_minutes=sch.interval_minutes,
        last_run_utc=sch.last_run_utc,
        last_status=sch.last_status,
        last_error=sch.last_error,
    )
