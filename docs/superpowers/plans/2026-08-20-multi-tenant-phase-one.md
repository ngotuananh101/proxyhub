# Multi-tenant Phase 1 — Tenant Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Tenant data model with User memberships, scope proxy/source/log/stats APIs per-tenant, migrate existing data to a default tenant.

**Architecture:** The backend gains a new `tenants` table, a `tenant_memberships` join table, and `tenant_id` foreign keys on the three existing tables (`proxies`, `proxysources`, `requestlogs`). A new dependency resolves the active tenant from a user's memberships and scopes all queries.

**Tech Stack:** FastAPI, SQLModel, PostgreSQL (psycopg v3), Alembic, Pytest, PyJWT.

## Global Constraints

- SQLModel table names lowercase verbatim: `tenants`, `tenant_memberships`.
- Default tenant: name `Default`, slug `default` — values verbatim.
- Existing databases migrate to a tenant slug `default` using Alembic + a data migration script in `scripts/`.
- Super admin bypasses tenant scoping. `user.is_admin` still guards `create/update/delete` of sources and settings.
- Backend only this phase. No frontend changes, no API keys, no gateway routing changes, no health-check per tenant.

---

### Task 1: Create Tenant model + service

**Files:**
- Create: `app/models/tenant.py`
- Modify: `app/models/__init__.py:1-7`
- Create: `app/services/tenant_service.py`

**Interfaces:**
- Produces: `Tenant` model (`.id`, `.name`, `.slug`, `.created_at`), `TenantMembership` model (`.id`, `.tenant_id`, `.user_id`, `.role`), exported from `app.models`.
- Produces: `tenant_service.ensure_default_tenant(session) -> Tenant` (idempotent, creates/returns `default`).

- [ ] **Step 1: Create Tenant model**

Create `app/models/tenant.py`:

```python
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
```

- [ ] **Step 2: Export models**

Replace `app/models/__init__.py`:

```python
from app.models.log import RequestLog
from app.models.proxy import Proxy, ProxyStatus
from app.models.setting import AppSetting
from app.models.source import ProxySource
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User

__all__ = [
    "User",
    "Proxy",
    "ProxyStatus",
    "AppSetting",
    "ProxySource",
    "RequestLog",
    "Tenant",
    "TenantMembership",
]
```

- [ ] **Step 3: Create `ensure_default_tenant`**

Create `app/services/tenant_service.py`:

```python
from sqlmodel import Session, select

from app.models.tenant import Tenant

DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "Default"


def ensure_default_tenant(session: Session) -> Tenant:
    """Create and return the default tenant. Idempotent."""
    tenant = session.exec(
        select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG)
    ).first()
    if tenant is None:
        tenant = Tenant(name=DEFAULT_TENANT_NAME, slug=DEFAULT_TENANT_SLUG)
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
    return tenant
```

- [ ] **Step 4: Run existing tests to ensure no regression**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (new model does not break existing).

- [ ] **Step 5: Commit**

```bash
git add app/models/tenant.py app/models/__init__.py app/services/tenant_service.py
git commit -m "feat: add Tenant and TenantMembership models"
```

---

### Task 2: Add tenant_id columns and tenant-scoped proxy selection

**Files:**
- Modify: `app/models/proxy.py:14-31`
- Modify: `app/models/source.py:7-18`
- Modify: `app/models/log.py:7-21`
- Modify: `app/services/proxy_service.py:67-76`
- Modify: `app/services/source_service.py:60-80`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Proxy.tenant_id`, `ProxySource.tenant_id`, `RequestLog.tenant_id` (all `Optional[int]`), and `select_random_proxy(session, tenant_id=None)`.

- [ ] **Step 1: Add tenant_id to Proxy model**

Replace `app/models/proxy.py`:

```python
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
        UniqueConstraint(
            "tenant_id", "scheme", "host", "port",
            name="uq_proxy_tenant_scheme_host_port",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenants.id", index=True)
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
```

- [ ] **Step 2: Add tenant_id to ProxySource model**

Replace `app/models/source.py`:

```python
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
    last_status: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 3: Add tenant_id to RequestLog model**

Replace `app/models/log.py`:

```python
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class RequestLog(SQLModel, table=True):
    __tablename__ = "requestlogs"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenants.id", index=True)
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
```

- [ ] **Step 4: Add tenant_id filter to `select_random_proxy`**

Replace `select_random_proxy` in `app/services/proxy_service.py:67-76`:

```python
def select_random_proxy(session: Session, tenant_id: int | None = None) -> Proxy | None:
    stmt = select(Proxy).where(
        Proxy.status == ProxyStatus.ALIVE,
        col(Proxy.scheme).in_(GATEWAY_SCHEMES),
    )
    if tenant_id is not None:
        stmt = stmt.where(Proxy.tenant_id == tenant_id)
    proxies = session.exec(stmt).all()
    if not proxies:
        return None
    return random.choice(proxies)
```

- [ ] **Step 5: Run test to verify existing behavior still passes**

Run: `python -m pytest tests/test_proxy_service.py tests/test_models.py -v`
Expected: PASS (note: `test_models.py` might reference unique constraint naming — fix if it asserts the old name).

- [ ] **Step 6: Commit**

```bash
git add app/models/proxy.py app/models/source.py app/models/log.py app/services/proxy_service.py
git commit -m "feat: add tenant_id columns and tenant-scoped proxy selection"
```

---

### Task 3: Alembic setup + migrations

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_add_tenants.py`
- Modify: `requirements.txt:15`
- Create: `scripts/migrate_to_tenants.py`
- Modify: `app/main.py:24-31`

**Interfaces:**
- Consumes: models from Task 2.
- Produces: alembic CLI + migration + data migration script.

- [ ] **Step 1: Add Alembic to requirements**

Append to `requirements.txt`:

```text
alembic>=1.13.0
```

- [ ] **Step 2: Create `alembic.ini`**

Create `alembic.ini`:

```ini
[alembic]
script_location = alembic
sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 3: Create `alembic/env.py`**

Create `alembic/env.py`:

```python
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from sqlmodel import SQLModel

from app.core.config import settings
from app.models import (  # noqa: F401
    AppSetting,
    Proxy,
    ProxySource,
    RequestLog,
    Tenant,
    TenantMembership,
    User,
)

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Create `alembic/script.py.mako`**

Create `alembic/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 5: Create initial migration**

Create `alembic/versions/0001_add_tenants.py`:

```python
"""add tenants

Revision ID: 0001
Revises:
Create Date: 2026-08-20

"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
    )
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])

    op.add_column("proxies", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.create_index("ix_proxies_tenant_id", "proxies", ["tenant_id"])
    op.add_column("proxysources", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.create_index("ix_proxysources_tenant_id", "proxysources", ["tenant_id"])
    op.add_column("requestlogs", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.create_index("ix_requestlogs_tenant_id", "requestlogs", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_requestlogs_tenant_id", table_name="requestlogs")
    op.drop_column("requestlogs", "tenant_id")
    op.drop_index("ix_proxysources_tenant_id", table_name="proxysources")
    op.drop_column("proxysources", "tenant_id")
    op.drop_index("ix_proxies_tenant_id", table_name="proxies")
    op.drop_column("proxies", "tenant_id")
    op.drop_index("ix_tenant_memberships_user_id", table_name="tenant_memberships")
    op.drop_index("ix_tenant_memberships_tenant_id", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
```

- [ ] **Step 6: Create data migration script**

Create `scripts/migrate_to_tenants.py`:

```python
"""One-time: create default tenant and assign existing rows to it."""
import sys

from sqlmodel import Session, select

from app.core.database import engine
from app.models import Proxy, ProxySource, RequestLog, User
from app.models.tenant import Tenant, TenantMembership
from app.services.tenant_service import ensure_default_tenant


def main() -> None:
    with Session(engine) as session:
        tenant = ensure_default_tenant(session)

        for model in (Proxy, ProxySource, RequestLog):
            rows = session.exec(select(model).where(model.tenant_id.is_(None))).all()
            for row in rows:
                row.tenant_id = tenant.id
                session.add(row)

        # Attach all existing users to the default tenant as admins
        users = session.exec(select(User)).all()
        for user in users:
            existing = session.exec(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant.id,
                    TenantMembership.user_id == user.id,
                )
            ).first()
            if existing is None:
                session.add(
                    TenantMembership(
                        tenant_id=tenant.id, user_id=user.id, role="admin"
                    )
                )

        session.commit()
        print(f"Migrated data to tenant '{tenant.slug}' (id={tenant.id})")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Verify migrations import cleanly**

Run: `python -c "import alembic; print(alembic.__version__)"`
Expected: prints version.

- [ ] **Step 8: Commit**

```bash
git add alembic.ini alembic/ scripts/migrate_to_tenants.py requirements.txt
git commit -m "chore: add Alembic and multi-tenant migration scaffolding"
```

---

### Task 4: Tenant + membership CRUD API (admin)

**Files:**
- Create: `app/api/tenants.py`
- Create: `app/schemas/tenant.py`
- Modify: `app/api/deps.py:32-41`
- Modify: `app/main.py:22-52`
- Test: `tests/test_tenants_api.py`

**Interfaces:**
- Consumes: `get_current_user`, `get_current_admin` from `app/api/deps.py`, `Tenant`/`TenantMembership` models.
- Produces: routes under `/api/tenants`:
  - `GET /api/tenants` → `list[TenantResponse]` (admin)
  - `POST /api/tenants` → `TenantResponse` (admin) body `{name, slug?}`
  - `GET /api/tenants/{tenant_id}/members` → `list[MembershipResponse]` (admin)
  - `POST /api/tenants/{tenant_id}/members` → `MembershipResponse` (admin) body `{user_id, role}`
  - `DELETE /api/tenants/{tenant_id}/members/{user_id}` → 204 (admin)

- [ ] **Step 1: Write failing tests**

Create `tests/test_tenants_api.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.security import hash_password
from app.models.user import User


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(engine, client):
    with Session(engine) as session:
        user = User(
            username="admin", hashed_password=hash_password("admin123"), is_admin=True
        )
        session.add(user)
        session.commit()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_tenant(client, auth_headers):
    resp = client.post(
        "/api/tenants",
        json={"name": "Acme", "slug": "acme"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "acme"
    assert data["name"] == "Acme"


def test_list_tenants(client, auth_headers):
    client.post(
        "/api/tenants",
        json={"name": "Acme", "slug": "acme"},
        headers=auth_headers,
    )
    resp = client.get("/api/tenants", headers=auth_headers)
    assert resp.status_code == 200
    slugs = [t["slug"] for t in resp.json()]
    assert "acme" in slugs


def test_add_membership(client, auth_headers, engine):
    with Session(engine) as session:
        user = User(
            username="bob", hashed_password=hash_password("bob123"), is_admin=False
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

    tenant_resp = client.post(
        "/api/tenants",
        json={"name": "Acme", "slug": "acme"},
        headers=auth_headers,
    )
    tenant_id = tenant_resp.json()["id"]

    resp = client.post(
        f"/api/tenants/{tenant_id}/members",
        json={"user_id": user_id, "role": "member"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "member"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tenants_api.py -v`
Expected: FAIL — router not found / model not defined.

- [ ] **Step 3: Create tenant schemas**

Create `app/schemas/tenant.py`:

```python
from pydantic import BaseModel


class TenantCreate(BaseModel):
    name: str
    slug: str | None = None


class TenantResponse(BaseModel):
    id: int
    name: str
    slug: str
    created_at: str


class MembershipCreate(BaseModel):
    user_id: int
    role: str = "member"


class MembershipResponse(BaseModel):
    id: int
    tenant_id: int
    user_id: int
    role: str
```

- [ ] **Step 4: Create tenants router**

Create `app/api/tenants.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.deps import get_current_admin
from app.core.database import get_session
from app.core.datetime_utils import utc_isoformat
from app.models.tenant import Tenant, TenantMembership, TenantRole
from app.models.user import User
from app.schemas.tenant import (
    MembershipCreate,
    MembershipResponse,
    TenantCreate,
    TenantResponse,
)

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


def _to_tenant_response(t: Tenant) -> TenantResponse:
    return TenantResponse(
        id=t.id,
        name=t.name,
        slug=t.slug,
        created_at=utc_isoformat(t.created_at),
    )


def _to_membership_response(m: TenantMembership) -> MembershipResponse:
    return MembershipResponse(
        id=m.id,
        tenant_id=m.tenant_id,
        user_id=m.user_id,
        role=m.role,
    )


@router.get("", response_model=list[TenantResponse])
def list_tenants(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    return [_to_tenant_response(t) for t in session.exec(select(Tenant)).all()]


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    body: TenantCreate,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    slug = body.slug or body.name.lower().replace(" ", "-")
    existing = session.exec(select(Tenant).where(Tenant.slug == slug)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Tenant slug already exists")
    tenant = Tenant(name=body.name, slug=slug)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    return _to_tenant_response(tenant)


@router.get("/{tenant_id}/members", response_model=list[MembershipResponse])
def list_members(
    tenant_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    return [
        _to_membership_response(m)
        for m in session.exec(
            select(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
        ).all()
    ]


@router.post("/{tenant_id}/members", response_model=MembershipResponse, status_code=status.HTTP_201_CREATED)
def add_member(
    tenant_id: int,
    body: MembershipCreate,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    if body.role not in (TenantRole.ADMIN, TenantRole.MEMBER):
        raise HTTPException(status_code=422, detail="role must be admin or member")
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    existing = session.exec(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == body.user_id,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="User already in tenant")
    membership = TenantMembership(
        tenant_id=tenant_id, user_id=body.user_id, role=body.role
    )
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return _to_membership_response(membership)


@router.delete("/{tenant_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    tenant_id: int,
    user_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_admin),
):
    membership = session.exec(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
        )
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")
    session.delete(membership)
    session.commit()
```

- [ ] **Step 5: Register router in `app/main.py`**

Add import:

```python
from app.api.tenants import router as tenants_router
```

Add:

```python
    app.include_router(tenants_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_tenants_api.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/api/tenants.py app/schemas/tenant.py app/api/deps.py app/main.py tests/test_tenants_api.py
git commit -m "feat: add tenant and membership CRUD API"
```

---

### Task 5: Tenant-aware dependencies and scoping (proxies, stats, logs, sources)

**Files:**
- Modify: `app/api/deps.py`
- Modify: `app/api/proxies.py`
- Modify: `app/api/stats.py`
- Modify: `app/api/logs.py`
- Modify: `app/api/sources.py`
- Modify: `app/schemas/proxy.py`
- Test: `tests/test_tenant_scoping.py`

**Interfaces:**
- Produces: `get_active_tenant_id`, `require_tenant_role`.

- [ ] **Step 1: Add tenant dependencies to `app/api/deps.py`**

Append to `app/api/deps.py`:

```python
from sqlmodel import Session, select

from app.models.tenant import TenantMembership


def get_active_tenant_id(
    current_user: User = Depends(get_current_user),
    x_tenant_id: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> int:
    if current_user.is_admin:
        memberships = session.exec(
            select(TenantMembership).where(TenantMembership.user_id == current_user.id)
        ).all()
    else:
        memberships = session.exec(
            select(TenantMembership).where(TenantMembership.user_id == current_user.id)
        ).all()
        if not memberships:
            raise HTTPException(status_code=403, detail="No tenant membership")

    if x_tenant_id is not None:
        try:
            requested = int(x_tenant_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid tenant id")
        if current_user.is_admin or any(m.tenant_id == requested for m in memberships):
            return requested
        raise HTTPException(status_code=403, detail="Not a member of this tenant")

    return memberships[0].tenant_id


def require_tenant_role(min_role: str):
    def dependency(
        current_user: User = Depends(get_current_user),
        x_tenant_id: str | None = Header(default=None),
        session: Session = Depends(get_session),
    ) -> User:
        membership = get_active_tenant_id(
            current_user=current_user,
            x_tenant_id=x_tenant_id,
            session=session,
        )
        if current_user.is_admin:
            return current_user
        m = session.exec(
            select(TenantMembership).where(
                TenantMembership.tenant_id == membership,
                TenantMembership.user_id == current_user.id,
                TenantMembership.role == min_role,
            )
        ).first()
        if m is None:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return current_user
    return dependency
```

- [ ] **Step 2: Write scoping tests**

Create `tests/test_tenant_scoping.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.security import hash_password
from app.models.user import User


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.main import create_app
    app = create_app(engine)
    return TestClient(app)


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(engine, client):
    with Session(engine) as session:
        user = User(
            username="admin", hashed_password=hash_password("admin123"), is_admin=True
        )
        session.add(user)
        session.commit()
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_proxy_sets_default_tenant(client, auth_headers):
    resp = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    # With super admin and no memberships, this defaults to first
    # membership or returns unscoped.
    assert "tenant_id" in data or data["id"] is not None
```

- [ ] **Step 3: Wire `get_active_tenant_id` into proxy list/create**

Modify `app/api/proxies.py`:

Change `list_proxies` signature to include:

```python
    tenant_id: int = Depends(get_active_tenant_id),
```

filter query:

```python
    query = select(Proxy).where(Proxy.tenant_id == tenant_id)
```

Change `create_proxy` signature:

```python
    tenant_id: int = Depends(get_active_tenant_id),
```

and add:

```python
    proxy = Proxy(**body.model_dump(), tenant_id=tenant_id)
```

Update unique-check in `create_proxy`:

```python
    existing = session.exec(
        select(Proxy).where(
            Proxy.tenant_id == tenant_id,
            Proxy.scheme == body.scheme,
            Proxy.host == body.host,
            Proxy.port == body.port,
        )
    ).first()
```

- [ ] **Step 4: Scope stats, logs, sources**

Modify `app/api/stats.py`:

```python
def stats_summary(
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_active_tenant_id),
):
    total = session.exec(
        select(func.count(Proxy.id)).where(Proxy.tenant_id == tenant_id)
    ).one()
    alive = session.exec(
        select(func.count(Proxy.id)).where(
            Proxy.tenant_id == tenant_id,
            Proxy.status == ProxyStatus.ALIVE,
        )
    ).one()
    ...
```

Modify `app/api/logs.py`:

See existing file structure. Filter by tenant in list query.

Modify `app/api/sources.py`:

Filter `list_sources` by tenant, `create_source` set tenant_id.

- [ ] **Step 5: Run tests to verify pass**

Run: `python -m pytest tests/test_proxies_api.py tests/test_tenant_scoping.py tests/test_stats_api.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/api/deps.py app/api/proxies.py app/api/stats.py app/api/logs.py app/api/sources.py app/schemas/proxy.py tests/test_tenant_scoping.py
git commit -m "feat: scope proxy, stats, logs, and sources APIs by tenant"
```

---

### Task 6: Migration to default tenant

**Files:**
- Modify: `app/main.py:24-31`
- Create: nothing new (scripts already in Task 3)
- Modify: `tests/test_models.py`

**Interfaces:**
- Consumes: `ensure_default_tenant` from Task 1.

- [ ] **Step 1: Seed default tenant in app startup**

In `app/main.py`, in `lifespan`, add `ensure_default_tenant` call alongside `seed_settings`:

```python
from app.services.tenant_service import ensure_default_tenant
...
        with Session(db_engine or engine) as session:
            seed_settings(session)
            seed_default_sources(session)
            ensure_default_tenant(session)
```

- [ ] **Step 2: Verify startup seed does not break**

Run: `python -m pytest tests/test_models.py tests/test_tenant_scoping.py -v`
Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest -q`
Expected: PASS (report count).

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: seed default tenant on startup"
```

---

## Self-Review Notes

After tasks, run `python -m pytest -q` and fix regressions. Confirmed in plan.
