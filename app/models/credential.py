from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class AuthMode:
    BASIC = "basic"
    IP_WHITELIST = "ip_whitelist"


class GatewayCredential(SQLModel, table=True):
    __tablename__ = "gateway_credentials"
    __table_args__ = (
        # The proxy sends a username with no tenant context, so basic-auth
        # usernames must be unique across tenants or the gateway cannot tell
        # which credential a request belongs to. NULL usernames (IP whitelist
        # rows) stay distinct in both SQLite and PostgreSQL.
        Index(
            "ix_gateway_credentials_auth_mode_username",
            "auth_mode",
            "username",
            unique=True,
        ),
    )

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
