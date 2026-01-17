import logging

from scales.scales import Scales

from ...config import settings
from ...models.device import Device
from ...security.fernet import decrypt_device_password

logger = logging.getLogger("app.integrations.mertech")


def get_scales(device: Device) -> Scales:
    """
    Фабрика клиента весов Mertech.
    """
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
        auto_reconnect=settings.auto_reconnect,
        connect_timeout=settings.connect_timeout,
        default_timeout=settings.default_timeout,
        retries=settings.retries,
        retry_delay=settings.retry_delay,
    )
