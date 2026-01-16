import logging
import json
from ..models import Device
from sqlalchemy.orm import Session

logger = logging.getLogger("app.services.products_cache")


def load_cached_products(device: Device) -> dict:
    device_id = getattr(device, "id", None)
    if not device.products_cache_json:
        logger.info("products_cache miss | device_id=%s", device_id)
        return {"products": []}

    try:
        data = json.loads(device.products_cache_json)
        products_count = (
            len(data.get("products", [])) if isinstance(data, dict) else "n/a"
        )
        logger.info(
            "products_cache hit | device_id=%s | cached_dirty=%s | count=%s",
            device_id,
            getattr(device, "cached_dirty", None),
            products_count,
        )
        return data
    except Exception:
        logger.exception("products_cache parse failed | device_id=%s", device_id)
        raise


def save_cached_products(
    db: Session, device: Device, products: dict, *, dirty: bool
) -> None:
    device_id = getattr(device, "id", None)
    try:
        device.products_cache_json = json.dumps(products, ensure_ascii=False)
    except Exception:
        logger.exception(
            "products_cache serialize failed | device_id=%s",
            device_id,
        )
        raise
    device.cached_dirty = dirty
    db.add(device)
    db.commit()
    db.refresh(device)
    logger.info(
        "products_cache saved | device_id=%s | dirty=%s",
        device_id,
        dirty,
    )
