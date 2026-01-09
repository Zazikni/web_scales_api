from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    debug: bool = False
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_minutes: int

    fernet_key: str
    scheduler_timezone: str
    cors_allow_origins: List[str] = []
    log_level: str = "INFO"

    scheduler_enabled: bool = False
    scheduler_interval: int = 1440
    products_fix_mode: bool = False


settings = Settings()
