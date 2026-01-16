import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from scales.exceptions import DeviceError

from ..db import SessionLocal
from ..models import AutoUpdateSchedule, Device
from . import fetch_products_and_cache, push_cache_to_scales, save_cached_products

logger = logging.getLogger("app.auto_update")


def utc_now_str() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def update_dates_only(products: dict) -> dict:
    today = datetime.now()
    fmt = "%d-%m-%y"

    items = products.get("products", [])
    if not isinstance(items, list):
        return products

    for p in items:
        if not isinstance(p, dict):
            continue
        shelf = int(p.get("shelfLifeInDays", 0) or 0)
        p["manufactureDate"] = today.strftime(fmt)
        p["sellByDate"] = (today + timedelta(days=shelf)).strftime(fmt)

    return products


def auto_update_job(device_id: int) -> None:
    """
    Выполнение одного прогона автоматического обновления по device_id.
    """
    db: Session = SessionLocal()
    try:
        device = db.get(Device, device_id)
        if not device:
            return

        sch = (
            db.query(AutoUpdateSchedule)
            .filter(AutoUpdateSchedule.device_id == device_id)
            .one_or_none()
        )
        if not sch or not sch.enabled:
            return

        # Обновление кэша товаров
        products = fetch_products_and_cache(db, device)

        # обновление дат и сохранение обновленных данных в кэш
        products = update_dates_only(products)
        save_cached_products(db, device, products, dirty=False)

        # Обновление товаров в устройстве
        push_cache_to_scales(db, device)

        # Фиксация результата операции
        sch.last_run_utc = utc_now_str()
        sch.last_status = "OK"
        sch.last_error = None
        db.add(sch)
        db.commit()

        logger.info("Auto-update OK: device_id=%d name=%s", device_id, device.name)

    except DeviceError as e:
        sch = (
            db.query(AutoUpdateSchedule)
            .filter(AutoUpdateSchedule.device_id == device_id)
            .one_or_none()
        )
        if sch:
            sch.last_run_utc = utc_now_str()
            sch.last_status = "ERROR"
            sch.last_error = str(e)
            db.add(sch)
            db.commit()
        logger.error("Auto-update DeviceError device_id=%d: %s", device_id, e)

    except Exception as e:
        sch = (
            db.query(AutoUpdateSchedule)
            .filter(AutoUpdateSchedule.device_id == device_id)
            .one_or_none()
        )
        if sch:
            sch.last_run_utc = utc_now_str()
            sch.last_status = "ERROR"
            sch.last_error = f"Unexpected: {e}"
            db.add(sch)
            db.commit()
        logger.exception("Auto-update unexpected device_id=%d: %s", device_id, e)

    finally:
        db.close()
