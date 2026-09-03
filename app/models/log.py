from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class RequestLog(SQLModel, table=True):
    __tablename__ = "requestlogs"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenants.id", index=True)
    auth_credential_id: Optional[int] = Field(
        default=None, foreign_key="gateway_credentials.id", index=True
    )
    auth_status: Optional[str] = Field(default=None)
    client_ip: Optional[str] = None
    method: Optional[str] = None
    host: Optional[str] = None
    path: Optional[str] = None
    proxy_host: Optional[str] = None
    proxy_port: Optional[int] = None
    response_bytes: Optional[int] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
