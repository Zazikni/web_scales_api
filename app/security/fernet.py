from cryptography.fernet import Fernet
from ..config import settings

_fernet = Fernet(settings.fernet_key.encode("utf-8"))


def encrypt_device_password(password: str) -> str:
    return _fernet.encrypt(password.encode("utf-8")).decode("utf-8")


def decrypt_device_password(password_encrypted: str) -> str:
    return _fernet.decrypt(password_encrypted.encode("utf-8")).decode("utf-8")
