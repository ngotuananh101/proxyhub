# Gateway Authentication Design Spec

**Date:** 2026-08-29
**Status:** Draft
**Scope:** Client authentication for the gateway port (8899) — per-tenant credentials (Basic auth and IP whitelist), a combined auth + proxy-selection endpoint, gateway plugin changes, request-log attribution, and a frontend management page.

---

## 1. Summary

Today anyone who can reach `:8899` uses the gateway anonymously. This spec adds client authentication at the gateway: each credential belongs to a tenant, supports either HTTP Basic auth (username + password) or IP whitelist (CIDR list), and determines which tenant's proxies the request is routed through and which tenant the access log is attributed to.

Chosen architecture (Approach A): the gateway forwards credentials to a **single combined backend endpoint** (`POST /internal/gateway/session`) that authenticates the client, selects an alive proxy scoped to the credential's tenant, and returns it. This keeps the current one round trip per connection, centralizes validation in the backend, and makes revocation effective immediately (within a short bcrypt cache TTL).

Non-goals: per-request rate limiting, per-credential quota accounting, and HTTPS termination at the gateway (clients use plain HTTP/CONNECT to the gateway as they do today; credentials travel as standard proxy Basic auth over the network the operator controls).

---

## 2. Data Model

### 2.1 New table `gateway_credentials`

New SQLModel `GatewayCredential` in `app/models/credential.py`, table `gateway_credentials`. Alembic migration `0002_add_gateway_credentials.py` creates the table and adds the two new columns to `requestlogs` (§2.2). Startup auto-patch in `app/core/database.py` gains cases for the new table and the new columns (same mechanism already used for `tenant_id`).

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `tenant_id` | int NOT NULL, FK `tenants.id`, indexed | Credential decides tenant (proxy pool + logs) |
| `name` | str NOT NULL | UI label, e.g. `team-a-crawler` |
| `auth_mode` | str NOT NULL | `basic` \| `ip_whitelist` |
| `username` | str?, unique per tenant | Set only for `basic`; unique constraint `(tenant_id, username)` over rows where `auth_mode = 'basic'` |
| `password_hash` | str? | bcrypt hash; only for `basic`; never returned by any API |
| `cidrs` | str? | Comma-separated CIDR entries; only for `ip_whitelist`; empty string and `None` both mean "matches nothing" |
| `is_active` | bool, default `True` | Toggle without deleting |
| `last_used_at` | datetime?, nullable | Updated on successful auth |
| `created_at` | datetime, default now(UTC) | |

Model-level validation (SQLModel validators): `auth_mode` must be one of the two values; `username` and `password_hash` required iff `auth_mode = 'basic'`; `cidrs` required iff `auth_mode = 'ip_whitelist'`. CIDR strings are validated with the `ipaddress` module at create/update time (single IPs stored as `/32` for v4, `/128` for v6).

`require_tenant_role("admin")` gates all mutations; membership users can read (list) credentials of their tenants.

### 2.2 RequestLog additions

`requestlogs` gains two nullable columns:

- `auth_credential_id` — FK `gateway_credentials.id`, which credential (if any) authenticated the request
- `auth_status` — str enum: `allowed` | `denied`; `NULL` for legacy rows

`RequestLogResponse` schema and the `/internal/logs` request model gain both fields; frontend logs table shows a red "denied" badge when `auth_status = 'denied'`.

---

## 3. Auth Flow — Combined Endpoint

### 3.1 Endpoint

`POST /internal/gateway/session` in `app/api/internal.py`, guarded by `verify_internal_key` (`X-Internal-Key`) exactly like the existing internal endpoints.

Request:

```json
{
  "username": "optional — present when client sent Basic auth",
  "password": "optional — present when client sent Basic auth",
  "client_ip": "required — gateway's view of the client address"
}
```

Processing order (deterministic):

1. **Basic auth attempted first.** If `username` present: find `GatewayCredential` where `auth_mode='basic'`, `username` matches, `is_active=True`. If found, verify password (bcrypt, via the cache in §3.3). Match → pass.
2. **IP whitelist fallback.** If no basic match (or no basic credentials sent): iterate active `ip_whitelist` credentials, parse `cidrs`, `ipaddress.ip_network(...)` membership check against `client_ip`. Match → pass.
3. **Both fail → HTTP 401** `{"detail": "Invalid credentials"}`. The gateway turns this into a 407 for the client and reports the denied attempt (§4).
4. **Pass →** `select_random_proxy(session, tenant_id=credential.tenant_id)` — reuses the existing tenant-scoped selection. No alive proxy in tenant → HTTP 404 `{"detail": "No available proxy"}` (gateway passes a 502 to the client).
5. Update `last_used_at` on the credential (same transaction).
6. Response:

```json
{
  "tenant_id": 1,
  "credential_id": 7,
  "auth_mode": "basic",
  "proxy": {"id": 1, "scheme": "http", "host": "1.2.3.4", "port": 8080,
            "username": null, "password": null},
  "default_target_url": "https://api.ipify.org"
}
```

`select_random_proxy` with a `tenant_id` that has no proxies returns `None` — behavior identical to today's unauthenticated path for an empty pool, except the pool is now tenant-scoped.

The response nests `proxy` fields under a `proxy` object rather than the flat shape used by `/internal/proxies`. The deprecated endpoint remains during transition; the plugin switches to the session endpoint.

### 3.2 Trusted-IP bypass

`X-Internal-Key` already identifies the gateway itself. The `internal` router requires it; no client-side IP trust is involved beyond the whitelist rules, which are purely operator-defined.

### 3.3 Bcrypt cache

Bcrypt verify costs ~100ms per check; the gateway opens one backend call per client connection. To keep p95 latency flat:

- In-process LRU cache (dict + lock, capped ~10_000 entries) in `app/services/gateway_auth_service.py`, keyed by `(credential_id, sha256(password))`, value = `verified_at` timestamp.
- Entry valid while `now - verified_at < GATEWAY_AUTH_CACHE_TTL` (new setting, default `60.0`, env-tunable; `0` disables caching entirely).
- `is_active` is re-checked on every session call, so deactivation takes effect immediately; a password *change* can lag by at most the TTL (worst case an old password keeps working ≤ 60s). Documented trade-off.

### 3.4 Denied-attempt logging

Failed session calls do not create a `RequestLog` row at session time — the plugin reports the full denied attempt after the client response in §4.4, carrying method/host/path metadata the session endpoint never sees.

---

## 4. Gateway Plugin

### 4.1 Session call

`before_upstream_connection` (in `app/gateway/plugin.py`):

1. Extract `Proxy-Authorization: Basic <b64(user:pass)>` header if present → base64-decode, split on first `:`.
2. Extract client IP from `self.client.addr` (the proxy library's client address tuple; falls back to the access-log `context["client_ip"]` when needed).
3. POST to the session endpoint (new env `GATEWAY_SESSION_URL`, derived from `GATEWAY_API_URL` exactly as `GATEWAY_LOG_URL` is derived today — `rsplit("/", 1)[0] + "/gateway/session"`).
4. `200` → initialize upstream with the returned proxy exactly as the current code does with `/internal/proxies` data; store `tenant_id`, `credential_id`, `auth_mode` on the plugin instance for the access log. The plugin builds `scheme://[user:pass@]host:port` from the nested `proxy` object, same as today.
5. `401` → construct an HTTP **407 Proxy Authentication Required** response with `Proxy-Authenticate: Basic realm="ProxyHub"` header; queue to client; do **not** connect upstream. Fire-and-forget `send_access_log` with `auth_status="denied"`, `credential_id=null`, empty proxy fields.
6. `404` (no proxy available) → 502 Bad Gateway to the client. Auth succeeded, so the access log reports `auth_status="allowed"` with the matched `credential_id` and empty proxy fields.
7. Network error / non-200 → 502 to the client, no upstream, log with `auth_status="allowed"`, empty proxy fields.

### 4.2 407 for CONNECT tunnels

For HTTPS CONNECT the client expects a 407 response line with the `Proxy-Authenticate` header. The plugin constructs the raw response bytes itself (`b"HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm=\"ProxyHub\"\r\nContent-Length: 0\r\n\r\n"`) and queues it to the client before closing the connection, for both plain HTTP requests and CONNECT tunnels.

### 4.3 Default-target rewrite and Proxy-Authorization to upstream

Unchanged from today: default-target rewrite logic and adding `Proxy-Authorization` toward the *upstream* proxy (using upstream credentials) stay as they are.

### 4.4 Access log payload

`send_access_log` payload gains:

```json
{
  "tenant_id": 1,
  "credential_id": 7,
  "auth_mode": "basic",
  "auth_status": "allowed",
  "client_ip": "...", "method": "...", "host": "...", "path": "...",
  "proxy_host": "5.6.7.8", "proxy_port": 8080, "response_bytes": 1234
}
```

- `auth_status="denied"` rows have `credential_id: null` (no credential matched, unknown identity) and empty proxy fields.
- `auth_status="allowed"` rows carry the matched credential and the proxy actually used. Connections that authenticated but found no proxy keep `credential_id` set and empty proxy fields.
- The `/internal/logs` request model accepts the new fields; the internal-key guard stays as is.

### 4.5 Startup guard

The gateway container starts before the backend may be reachable; this is today's behavior (per-connection failure, `fetch_proxy_from_api` returns `None` → connection refused) and does not change with this design. No new startup dependency.

### 4.6 New environment variables

| Env | Default | Purpose |
|---|---|---|
| `GATEWAY_SESSION_URL` | derived from `GATEWAY_API_URL` | Where the plugin posts session requests |
| `GATEWAY_AUTH_CACHE_TTL` | `60` | Backend-side bcrypt cache TTL, seconds |

`.env.example` documents both.

---

## 5. Management CRUD API

`app/api/gateway_credentials.py`, router `/api/gateway-credentials` (all under existing JWT auth):

| Endpoint | Auth | Notes |
|---|---|---|
| `GET /` | `get_current_user` + tenant scoping | List credentials for the active tenant (from `get_active_tenant_id`); response omits `password_hash`, includes `last_used_at`, `is_active`. Non-admins see only tenants they belong to; admins can switch active tenant as with other pages |
| `POST /` | `require_tenant_role("admin")` | Create. Validates mode-specific fields, validates CIDR entries. For `basic`: username required, password **generated server-side** and returned in plaintext **once** in the create response; hash stored |
| `PATCH /{id}` | `require_tenant_role("admin")` | Rename, rotate password (returns new plaintext once), edit CIDRs, toggle `is_active`. Enforces same field/mode rules as create |
| `DELETE /{id}` | `require_tenant_role("admin")` | Delete row. Historical request logs keep their `auth_credential_id` value (FK is `ON DELETE SET NULL` — rows survive credential deletion) |

The `require_tenant_role("admin")` dependency resolves the tenant from the `X-Tenant-Id` header via `get_active_tenant_id` — same as existing tenant-scoped routes, so the TenantSwitcher keeps working unchanged.

Rollback semantics: revocation means row delete or `is_active=False`; deactivation takes effect on the next connection immediately, a rotated password can keep working ≤ cache TTL.

---

## 6. Frontend

New page `GatewayCredentialsPage` at route `/credentials` (sidebar entry **Gateway**):

- Table: name, auth-mode badge (Basic / IP whitelist), username or CIDR summary, tenant name, `last_used_at`, active toggle (switch), delete button with confirm dialog.
- Create dialog: radio **Basic** / **IP whitelist**:
  - Basic → name + username; password is generated server-side and shown once in a follow-up dialog with a copy button and example client URL `http://user:pass@host:8899`.
  - IP whitelist → name + textarea of CIDR entries (one per line), client-side validation per line, server-side re-validation.
- Rotate password action on each basic row (opens same one-time-password dialog).
- Edit CIDRs action on whitelist rows.
- `src/api/credentials.ts` — typed client following the existing `sources.ts` pattern.
- TenantSwitcher continues to scope the page via the `X-Tenant-Id` interceptor.
- LogsPage: show a red **denied** badge on rows with `auth_status="denied"`.

API responses never include `password_hash` or any retrievable password after creation/rotation.

---

## 7. Testing

Backend (pytest):

1. Model validation: mode-specific required fields; CIDR format validation (rejects garbage, accepts single IP, expands to /32).
2. CRUD: create basic (password generated + returned once, hash stored), create whitelist (CIDRs stored), rotate password, toggle active, delete; role gate (member 403, admin 200); tenant isolation (tenant A admin cannot touch tenant B rows — same pattern as existing tenant tests).
3. Session endpoint: basic happy path (alive proxy of the right tenant returned); wrong password 401; unknown user 401; whitelist match v4 and v6; whitelist non-match 401; both-supplied-but-both-fail 401; inactive credential 401; no alive proxy 404; `last_used_at` updated; internal-key guard (missing/incorrect `X-Internal-Key` 401).
4. Bcrypt cache: second call with same password hits cache (injected clock); TTL expiry re-verifies; `GATEWAY_AUTH_CACHE_TTL=0` disables.

Gateway (existing gateway test setup):

5. 407 construction for plain HTTP and CONNECT; access-log payload carries new fields; session call includes client IP and decoded Basic credentials; behavior when backend returns 401 / 404 / network error.
6. Existing plugin tests updated to the session endpoint (mocked `httpx` responses adjusted to nested `proxy` shape).

Frontend (vitest + RTL):

7. Page renders rows; create-basic flow shows one-time password dialog; create-whitelist flow validates CIDR lines; delete confirm; denied badge on logs page.

---

## 8. Migration & Rollout

1. Alembic `0002_add_gateway_credentials.py` creates `gateway_credentials` and adds `auth_credential_id` + `auth_status` to `requestlogs` (FK `ON DELETE SET NULL`).
2. `app/core/database.py` auto-patch: add the new table/columns to the legacy-table patcher so existing Postgres deployments (which missed `0001`) upgrade automatically on startup, same as `tenant_id` handling today. `0002` alone is insufficient for already-running deployments that never ran alembic — that is exactly why the auto-patch exists.
3. docker-compose unchanged; new env vars documented in `.env.example`.
4. Rollout order within one release: backend first (migration + session endpoint + CRUD), then the plugin switch, then the frontend page. The old `/internal/proxies` route stays for one transition release before removal in a follow-up.

### 8.1 Settings registry

`GATEWAY_AUTH_CACHE_TTL` is an infrastructure setting, not a tenant-facing knob: add to `app/core/config.py` Settings (env-tunable) only, not to `settings_registry.py` (which holds user-facing UI settings).

---

## 9. Open Questions

None — all decisions captured above.
