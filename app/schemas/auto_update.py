from pydantic import BaseModel, Field


class AutoUpdateConfig(BaseModel):
    enabled: bool
    interval_minutes: int = Field(ge=1)
    last_run_utc: str | None = None
    last_status: str | None = None
    last_error: str | None = None
