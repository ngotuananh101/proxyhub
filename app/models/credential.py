from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class AuthMode:
    BASIC = "basic"
    IP_WHITELIST = "ip_whitelist"


class GatewayCredential(SQLModel, table=True):
    __tablename__ = "gateway_credentials"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    name: str
    auth_mode: str = Field(index=True)
    username: Optional[str] = Field(default=None, index=True)
    password_hash: Optional[str] = Field(default=None)
    cidrs: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)
    last_used_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
