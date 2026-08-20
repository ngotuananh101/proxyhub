# Multi-tenant Phase 1 — Tenant Foundations Design Spec

**Date:** 2026-08-20
**Status:** Draft
**Approach:** Alembic + migration, default tenant

## Summary

Add the foundational tenant data model and scope existing proxy, source, log and stats APIs per-tenant. Seed a `default` tenant and migrate pre-existing rows to it. This does NOT include API keys, gateway routing changes, or frontend UI yet — those are later phases.

## Scope Decisions

| Decision | Choice |
|---|---|
| Tenant model semantics | SaaS — isolation per tenant |
| Tenant identification | `slug` unique (name non-unique, only for display) |
| User↔tenant relation | User can belong to multiple tenants (membership) |
| How gateway identifies tenant | API Key (Phase 2, not in this phase) |
| Existing data | Migrate to default tenant |
| Migration approach | Alembic + default tenant |
| Super admin | Super admin views tenant selector (see all tenants) |

## Phase 1 Out of Scope

- API Keys (Phase 2)
- Gateway routing by tenant (Phase 2)
- Frontend tenant selector / API Keys UI (Phase 3)
- Health-check per-tenant (still global for now)
- Edit Proxy dialog already done — this phase may touch it again only minimally.

## Data Model

### New tables

#### `tenants`

| Col | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `name` | str | display, not unique |
| `slug` | str | unique, used in URLs |
| `created_at` | datetime | |

#### `tenant_memberships`

| Col | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `tenant_id` | FK → tenants.id | |
| `user_id` | FK → users.id | |
| `role` | str | `admin` or `member` |

### Existing tables gain columns

| Table | Column |
|---|---|
| `proxies` | `tenant_id` FK, nullable initially |
| `proxysources` | `tenant_id` FK, nullable |
| `requestlogs` | `tenant_id` FK, nullable |

### Proxy constraint changes

From:
```
UniqueConstraint("scheme", "host", "port", name="uq_proxy_scheme_host_port")
```

To:
```
UniqueConstraint("tenant_id", "scheme", "host", "port", name="uq_proxy_tenant_scheme_host_port")
```

## Backend changes

### Deps (`app/api/deps.py`)

- `get_active_tenant_id` — resolve tenant for user, preferring `X-Tenant-Id` header (if the user is a member of that tenant), else user's first membership tenant.
- `require_tenant_role(role)` — factory to check the active membership's role.
- `get_current_admin` stays. Super admin bypasses tenant scoping (sees all tenants).

### Scoped APIs

`tenant_id = get_active_tenant_id(...)` for users; super adminds can use `X-Tenant-Id` or membership default.

- `app/api/proxies.py`: `list_proxies` filters by tenant, `create_proxy` sets tenant_id, `update/get/delete` verify tenant. `delete_many`.
- `app/api/stats.py`: count only within tenant.
- `app/api/logs.py`: filter only within current tenant.
- `app/api/sources.py`: scoped.

### Internal / gateway

Not changed in this phase. `GET /internal/proxies` still uses `select_random_proxy` (random across all pools) — unchanged until Phase 2.

## Migration

### Alembic setup
- `alembic.ini`, `alembic/env.py`
- Dependency add: `alembic`, `psycopg2-binary` (already present)

### Alembic migration
- `alembic/versions/0001_add_tenants.py`
- Creates `tenants` and `tenant_memberships` tables
- Adds `tenant_id` columns to `proxies`, `proxysources`, `requestlogs`

### Data migration script
- `scripts/migrate_to_tenants.py`
- Creates default tenant and assigns existing table rows to it.

### Seed in app
Extend startup to call `ensure_default_tenant(session)`.

## Tests

- tenant CRUD (create/list)
- membership assignment + role check
- proxy scoped per tenant: user in tenant A cannot see tenant B's proxies
- migration path (default tenant + data lands in default)

## Out of Scope (reference)

See above.
