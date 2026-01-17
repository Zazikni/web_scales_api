from pydantic import BaseModel, Field


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    ip: str = Field(min_length=1, max_length=64)
    port: int = Field(ge=1, le=65535, default=1111)
    protocol: str = Field(pattern="^(TCP)$", default="TCP")
    password: str = Field(min_length=1, max_length=64)


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    ip: str | None = Field(default=None, min_length=1, max_length=64)
    port: int | None = Field(default=None, ge=1, le=65535)
    protocol: str | None = Field(default=None, pattern="^(TCP)$")
    password: str | None = Field(default=None, min_length=1, max_length=64)


class DeviceOut(BaseModel):
    id: int
    name: str
    description: str
    ip: str
    port: int
    protocol: str
    cached_dirty: bool

    class Config:
        from_attributes = True
