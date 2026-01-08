import json
import time
from contextlib import contextmanager
from typing import Any, Iterator

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from .config import settings
from .models import Device

from scales import Scales
from scales.exceptions import DeviceError
import logging

logger = logging.getLogger("app.scales_client")

_fernet = Fernet(settings.fernet_key.encode("utf-8"))


@contextmanager
def _timed(op: str, **fields: Any) -> Iterator[None]:
    """
    Контекстный менеджер для логирования старта/успеха/ошибки операции
    с измерением длительности.
    """
    start = time.perf_counter()
    logger.info("start %s | %s", op, fields)
    try:
        yield
        dur_ms = int((time.perf_counter() - start) * 1000)
        logger.info("success %s | duration_ms=%s | %s", op, dur_ms, fields)
    except Exception:
        dur_ms = int((time.perf_counter() - start) * 1000)
        logger.exception("fail %s | duration_ms=%s | %s", op, dur_ms, fields)
        raise


def encrypt_device_password(password: str) -> str:
    return _fernet.encrypt(password.encode("utf-8")).decode("utf-8")


def decrypt_device_password(password_encrypted: str) -> str:
    return _fernet.decrypt(password_encrypted.encode("utf-8")).decode("utf-8")


def get_scales(device: Device) -> Scales:
    password = decrypt_device_password(device.password_encrypted)
    device_id = getattr(device, "id", None)
    logger.debug(
        "create scales client | device_id=%s | ip=%s | port=%s | protocol=%s",
        device_id,
        device.ip,
        device.port,
        device.protocol,
    )
    return Scales(
        device.ip,
        device.port,
        password,
        device.protocol,
        auto_reconnect=True,
        connect_timeout=3.0,
        default_timeout=5.0,
        retries=2,
        retry_delay=0.5,
    )


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


def validate_plu_uniqueness(products: dict) -> None:
    items = products.get("products", [])
    if not isinstance(items, list):
        raise DeviceError("Некорректный формат: поле products должно быть массивом.")

    seen = set()
    for p in items:
        if not isinstance(p, dict):
            continue
        if "plu" not in p:
            continue
        key = str(p["plu"])
        if key in seen:
            raise DeviceError(
                f"Нарушение уникальности plu в рамках устройства: plu={key}"
            )
        seen.add(key)


def fetch_products_and_cache(db: Session, device: Device) -> dict:
    device_id = getattr(device, "id", None)
    fields = {
        "device_id": device_id,
        "ip": device.ip,
        "port": device.port,
        "protocol": device.protocol,
    }

    with _timed("scales.fetch_products_and_cache", **fields):
        scales = get_scales(device)

        logger.info(
            "fetch products from scales | device_id=%s | ip=%s | port=%s | protocol=%s",
            device_id,
            device.ip,
            device.port,
            device.protocol,
        )

        products = scales.get_products_json()

        products_count = (
            len(products.get("products", [])) if isinstance(products, dict) else "n/a"
        )
        logger.info(
            "fetch products result | device_id=%s | count=%s",
            device_id,
            products_count,
        )

        validate_plu_uniqueness(products)
        save_cached_products(db, device, products, dirty=False)
        return products


def push_cache_to_scales(db: Session, device: Device) -> None:
    device_id = getattr(device, "id", None)
    fields = {
        "device_id": device_id,
        "ip": device.ip,
        "port": device.port,
        "protocol": device.protocol,
    }

    with _timed("scales.push_cache_to_scales", **fields):
        if not device.products_cache_json:
            logger.warning(
                "push cache skipped | device_id=%s | reason=no_cache", device_id
            )
            raise DeviceError(
                "Нет кэша товаров для загрузки. Сначала выполните выгрузку товаров с весов."
            )

        scales = get_scales(device)
        products = load_cached_products(device)

        products_count = (
            len(products.get("products", [])) if isinstance(products, dict) else "n/a"
        )
        logger.info(
            "push cache to scales | device_id=%s | count=%s | cached_dirty=%s",
            device_id,
            products_count,
            getattr(device, "cached_dirty", None),
        )

        validate_plu_uniqueness(products)

        scales.send_json_products(products)

        device.cached_dirty = False
        db.add(device)
        db.commit()
        db.refresh(device)

        logger.info(
            "push cache completed | device_id=%s | cached_dirty=%s",
            device_id,
            device.cached_dirty,
        )
