from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class ProxySource(SQLModel, table=True):
    __tablename__ = "proxysources"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenants.id", index=True)
    name: str
    url: str
    enabled: bool = Field(default=True, index=True)
    interval_minutes: int = Field(default=60)
    last_fetched_at: Optional[datetime] = None
    last_status: Optional[str] = None  # e.g. "ok: 120 imported, 340 duplicates" or "error: ..."
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
