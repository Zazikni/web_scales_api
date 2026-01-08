# app/logging_config.py
from __future__ import annotations

from logging.config import dictConfig


def setup_logging(level: str = "INFO") -> None:
    """
    Централизованная настройка logging для приложения и uvicorn.
    - Управляется через .env (LOG_LEVEL)
    """
    level = (level or "INFO").upper()

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                },
                "access": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": level,
                },
            },
            "loggers": {
                # Логгеры приложения
                "app": {"handlers": ["console"], "level": level, "propagate": False},
                # Логгеры uvicorn
                "uvicorn": {"handlers": ["console"], "level": level, "propagate": False},
                "uvicorn.error": {
                    "handlers": ["console"],
                    "level": level,
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["console"],
                    "level": level,
                    "propagate": False,
                },
            },
            # Root на случай сторонних библиотек
            "root": {"handlers": ["console"], "level": level},
        }
    )
