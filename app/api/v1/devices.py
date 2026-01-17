import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_user_device_or_404, get_current_user
from app.models import User, Device, AutoUpdateSchedule
from app.schemas import (
    DeviceCreate,
    DeviceUpdate,
    DeviceOut,
)
from app.config import settings
from app.security import encrypt_device_password
from app.services.scheduler_service import scheduler_rebuild_jobs_from_db

logger = logging.getLogger("app.main")

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    logger.info(
        "list devices | user_id=%s",
        user.id,
    )
    return db.query(Device).filter(Device.owner_id == user.id).all()


@router.post("", response_model=DeviceOut, status_code=201)
def create_device(
    req: DeviceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "create device requested | user_id=%s | name=%s | ip=%s | port=%s | protocol=%s",
        user.id,
        req.name,
        req.ip,
        req.port,
        req.protocol,
    )
    dev = Device(
        owner_id=user.id,
        name=req.name,
        description=req.description,
        ip=req.ip,
        port=req.port,
        protocol=req.protocol,
        password_encrypted=encrypt_device_password(req.password),
        products_cache_json=None,
        cached_dirty=False,
    )
    db.add(dev)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.warning(
            "create device failed | user_id=%s | name=%s | reason=name_conflict",
            user.id,
            req.name,
        )
        raise HTTPException(
            status_code=409, detail="Device with this name already exists"
        )

    db.refresh(dev)

    sch = AutoUpdateSchedule(
        device_id=dev.id,
        enabled=settings.scheduler_enabled,
        interval_minutes=settings.scheduler_interval,
        last_run_utc=None,
        last_status=None,
        last_error=None,
    )
    db.add(sch)
    db.commit()
    logger.info(
        "create device success | user_id=%s | device_id=%s | name=%s",
        user.id,
        dev.id,
        dev.name,
    )
    scheduler_rebuild_jobs_from_db()
    return dev


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "get device requested | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    device = get_user_device_or_404(db, user.id, device_id)

    logger.info(
        "get device success | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    return device


@router.put("/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: int,
    req: DeviceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "update device requested | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    dev = get_user_device_or_404(db, user.id, device_id)

    if req.name is not None:
        dev.name = req.name
    if req.description is not None:
        dev.description = req.description
    if req.ip is not None:
        dev.ip = req.ip
    if req.port is not None:
        dev.port = req.port
    if req.protocol is not None:
        dev.protocol = req.protocol
    if req.password is not None:
        dev.password_encrypted = encrypt_device_password(req.password)

    db.add(dev)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.warning(
            "update device failed | user_id=%s | device_id=%s | reason=name_conflict",
            user.id,
            device_id,
        )
        raise HTTPException(status_code=409, detail="Device name conflict")
    db.refresh(dev)
    logger.info(
        "update device success | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    return dev


@router.delete("/{device_id}", status_code=204)
def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(
        "delete device requested | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    dev = get_user_device_or_404(db, user.id, device_id)
    db.delete(dev)
    db.commit()
    logger.info(
        "delete device success | user_id=%s | device_id=%s",
        user.id,
        device_id,
    )
    if settings.scheduler_enabled:
        scheduler_rebuild_jobs_from_db()
    else:
        logger.info("scheduler disabled | skip rebuild_jobs_from_db")
    return None
