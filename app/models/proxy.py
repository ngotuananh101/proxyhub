import enum
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class ProxyStatus(str, enum.Enum):
    UNKNOWN = "unknown"
    ALIVE = "alive"
    DEAD = "dead"


class Proxy(SQLModel, table=True):
    __tablename__ = "proxies"
    __table_args__ = (
        UniqueConstraint("scheme", "host", "port", name="uq_proxy_scheme_host_port"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    scheme: str = Field(index=True)  # http | https
    host: str = Field(index=True)
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    status: ProxyStatus = Field(default=ProxyStatus.UNKNOWN, index=True)
    latency_ms: Optional[float] = None
    last_checked_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
