from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class TenantRole:
    ADMIN = "admin"
    MEMBER = "member"


class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(unique=True, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class TenantMembership(SQLModel, table=True):
    __tablename__ = "tenant_memberships"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    role: str = Field(default=TenantRole.MEMBER)
