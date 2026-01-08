from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str

    jwt_secret_key: str
    jwt_algorithm: str
    jwt_access_token_minutes: int

    fernet_key: str
    scheduler_timezone: str
    cors_allow_origins: List[str] = []
    log_level: str = "INFO"


settings = Settings()
