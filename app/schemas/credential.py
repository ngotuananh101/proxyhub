from typing import Literal

from pydantic import BaseModel, field_validator


class GatewayCredentialCreate(BaseModel):
    name: str
    auth_mode: Literal["basic", "ip_whitelist"]
    username: str | None = None
    cidrs: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Name cannot be empty")
        return s


class GatewayCredentialUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    cidrs: str | None = None
    rotate_password: bool = False


class GatewayCredentialResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    auth_mode: str
    username: str | None = None
    cidrs: str | None = None
    is_active: bool
    last_used_at: str | None = None
    created_at: str


class GatewayCredentialCreatedResponse(GatewayCredentialResponse):
    generated_password: str | None = None


class GatewayCredentialListResponse(BaseModel):
    items: list[GatewayCredentialResponse]
    total: int
