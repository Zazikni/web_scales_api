import logging

from fastapi import Depends
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .api.router import api_router
from .config import settings
from .db import Base, engine, get_db
from .deps import get_current_user, get_user_device_or_404
from .logging_config import setup_logging
from .models import User, AutoUpdateSchedule
from .schemas import (
    AutoUpdateConfig,
)
from .services.scheduler_service import (
    scheduler_rebuild_jobs_from_db,
    scheduler_start,
    scheduler_shutdown,
)

setup_logging(settings.log_level)
logger = logging.getLogger("app.main")

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Scales API",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
)
logger.info("Application started")
logger.info("CORS origins: %s", settings.cors_allow_origins)
logger.info("Database URL: %s", settings.database_url)

app.include_router(api_router)

origins = settings.cors_allow_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    scheduler_start()
    scheduler_rebuild_jobs_from_db()


@app.on_event("shutdown")
def shutdown():
    scheduler_shutdown()


# ---------- devices ----------


# ---------- products ----------


# ---------- auto update ----------


@app.get("/devices/{device_id}/auto-update", response_model=AutoUpdateConfig)
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


@app.put("/devices/{device_id}/auto-update", response_model=AutoUpdateConfig)
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
