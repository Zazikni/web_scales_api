import json
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from .config import settings
from .models import Device

from scales import Scales
from scales.exceptions import DeviceError
import logging

logger = logging.getLogger("app.scales_client")

_fernet = Fernet(settings.fernet_key.encode("utf-8"))


def encrypt_device_password(password: str) -> str:
    return _fernet.encrypt(password.encode("utf-8")).decode("utf-8")


def decrypt_device_password(password_encrypted: str) -> str:
    return _fernet.decrypt(password_encrypted.encode("utf-8")).decode("utf-8")


def get_scales(device: Device) -> Scales:
    password = decrypt_device_password(device.password_encrypted)
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
    if not device.products_cache_json:
        return {"products": []}
    return json.loads(device.products_cache_json)


def save_cached_products(
    db: Session, device: Device, products: dict, *, dirty: bool
) -> None:
    device.products_cache_json = json.dumps(products, ensure_ascii=False)
    device.cached_dirty = dirty
    db.add(device)
    db.commit()
    db.refresh(device)


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
    scales = get_scales(device)
    products = scales.get_products_json()
    validate_plu_uniqueness(products)
    save_cached_products(db, device, products, dirty=False)
    return products


def push_cache_to_scales(db: Session, device: Device) -> None:
    if not device.products_cache_json:
        raise DeviceError(
            "Нет кэша товаров для загрузки. Сначала выполните выгрузку товаров с весов."
        )
    scales = get_scales(device)
    products = load_cached_products(device)
    validate_plu_uniqueness(products)
    scales.send_json_products(products)
    device.cached_dirty = False
    db.add(device)
    db.commit()
    db.refresh(device)
