from pydantic import BaseModel, EmailStr, Field
from typing import Any


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


# class LoginRequest(BaseModel):
#     email: EmailStr
#     password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"



class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    ip: str = Field(min_length=1, max_length=64)
    port: int = Field(ge=1, le=65535, default=1111)
    protocol: str = Field(pattern="^(TCP|UDP)$", default="TCP")
    password: str = Field(min_length=1, max_length=64)


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    ip: str | None = Field(default=None, min_length=1, max_length=64)
    port: int | None = Field(default=None, ge=1, le=65535)
    protocol: str | None = Field(default=None, pattern="^(TCP|UDP)$")
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



class ProductsResponse(BaseModel):
    products: Any  # полный JSON от весов


class ProductPatchRequest(BaseModel):
    fields: dict[str, Any]


class AutoUpdateConfig(BaseModel):
    enabled: bool
    interval_minutes: int = Field(ge=1)
    last_run_utc: str | None = None
    last_status: str | None = None
    last_error: str | None = None
