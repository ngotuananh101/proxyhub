# Edit Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to edit all proxy fields (scheme, host, port, username, password, status) via a dialog triggered by an Edit icon on each table row.

**Architecture:** Extend the existing `PUT /api/proxies/{id}` endpoint to accept `scheme` and `status` fields with validation. On the frontend, create a new `EditProxyDialog` component (mirroring `AddProxyDialog` pattern), add an Edit icon to `ProxyTable`, and wire it up in `ProxiesPage`.

**Tech Stack:** FastAPI + SQLModel (backend), React + TanStack Query + shadcn/ui base-sera (frontend), pytest (tests)

## Global Constraints

- shadcn style: base-sera (square corners, border=0). Never hand-edit generated `ui/` components.
- App is wrapped in `TooltipProvider`.
- Frontend uses axios via `frontend/src/api/client.ts`.
- Backend uses `ProxyStatus` enum: `UNKNOWN`, `ALIVE`, `DEAD`.
- Unique constraint on `(scheme, host, port)`.

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `app/schemas/proxy.py` | Add `scheme` and `status` to `ProxyUpdate` |
| Modify | `app/api/proxies.py` | Validation + unique check in `update_proxy()` |
| Modify | `tests/test_proxies_api.py` | Tests for update endpoint |
| Modify | `frontend/src/api/proxies.ts` | `updateProxy()` API function |
| Create | `frontend/src/components/proxies/EditProxyDialog.tsx` | Edit dialog component |
| Modify | `frontend/src/components/proxies/ProxyTable.tsx` | Add `onEdit` prop + PencilIcon |
| Modify | `frontend/src/pages/ProxiesPage.tsx` | Wire up EditProxyDialog |

---

### Task 1: Backend — Extend ProxyUpdate schema and update endpoint with validation

**Files:**
- Modify: `app/schemas/proxy.py:12-16`
- Modify: `app/api/proxies.py:131-147`
- Test: `tests/test_proxies_api.py`

**Interfaces:**
- Consumes: `Proxy` model, `ProxyStatus` enum from `app/models/proxy.py`
- Produces: `PUT /api/proxies/{id}` accepts `scheme`, `host`, `port`, `username`, `password`, `status` (all optional). Returns `ProxyResponse`. 409 on duplicate `(scheme, host, port)`. 422 on invalid scheme/status.

- [ ] **Step 1: Write failing tests for the update endpoint**

Add these tests to `tests/test_proxies_api.py`:

```python
def test_update_proxy_host(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"host": "5.6.7.8"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["host"] == "5.6.7.8"
    assert resp.json()["port"] == 8080  # unchanged


def test_update_proxy_scheme(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"scheme": "https"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["scheme"] == "https"


def test_update_proxy_status(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"status": "alive"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


def test_update_proxy_invalid_scheme(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"scheme": "socks5"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_update_proxy_invalid_status(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"status": "bananas"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_update_proxy_duplicate_conflict(client, auth_headers):
    client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.1.1.1", "port": 80},
        headers=auth_headers,
    )
    create2 = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "2.2.2.2", "port": 80},
        headers=auth_headers,
    )
    proxy2_id = create2.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy2_id}",
        json={"host": "1.1.1.1"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_update_proxy_same_values_no_conflict(client, auth_headers):
    create = client.post(
        "/api/proxies",
        json={"scheme": "http", "host": "1.2.3.4", "port": 8080},
        headers=auth_headers,
    )
    proxy_id = create.json()["id"]
    resp = client.put(
        f"/api/proxies/{proxy_id}",
        json={"host": "1.2.3.4"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


def test_update_proxy_not_found(client, auth_headers):
    resp = client.put(
        "/api/proxies/99999",
        json={"host": "1.1.1.1"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_proxies_api.py::test_update_proxy_scheme tests/test_proxies_api.py::test_update_proxy_status tests/test_proxies_api.py::test_update_proxy_invalid_scheme tests/test_proxies_api.py::test_update_proxy_invalid_status tests/test_proxies_api.py::test_update_proxy_duplicate_conflict -v`

Expected: Some tests FAIL (scheme/status not accepted, no validation, no duplicate check).

- [ ] **Step 3: Update ProxyUpdate schema**

In `app/schemas/proxy.py`, replace the `ProxyUpdate` class:

```python
class ProxyUpdate(BaseModel):
    scheme: str | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    status: str | None = None
```

- [ ] **Step 4: Update the update_proxy endpoint with validation**

In `app/api/proxies.py`, add `datetime` import at the top:

```python
from datetime import datetime, timezone
```

Replace the `update_proxy` function (lines 131-147):

```python
@router.put("/{proxy_id}", response_model=ProxyResponse)
def update_proxy(
    proxy_id: int,
    body: ProxyUpdate,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    proxy = session.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")

    update_data = body.model_dump(exclude_unset=True)

    # Validate scheme
    if "scheme" in update_data and update_data["scheme"] not in ("http", "https"):
        raise HTTPException(status_code=422, detail="Scheme must be http or https")

    # Validate status → convert to enum
    if "status" in update_data:
        try:
            update_data["status"] = ProxyStatus(update_data["status"])
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="Status must be alive, dead, or unknown",
            )

    # Check unique constraint when scheme/host/port changes
    new_scheme = update_data.get("scheme", proxy.scheme)
    new_host = update_data.get("host", proxy.host)
    new_port = update_data.get("port", proxy.port)
    if (new_scheme, new_host, new_port) != (proxy.scheme, proxy.host, proxy.port):
        conflict = session.exec(
            select(Proxy).where(
                Proxy.scheme == new_scheme,
                Proxy.host == new_host,
                Proxy.port == new_port,
                Proxy.id != proxy_id,
            )
        ).first()
        if conflict:
            raise HTTPException(status_code=409, detail="Proxy already exists")

    for key, value in update_data.items():
        setattr(proxy, key, value)
    proxy.updated_at = datetime.now(timezone.utc)
    session.add(proxy)
    session.commit()
    session.refresh(proxy)
    return _proxy_to_response(proxy)
```

- [ ] **Step 5: Run all tests to verify they pass**

Run: `python -m pytest tests/test_proxies_api.py -v`

Expected: ALL tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/schemas/proxy.py app/api/proxies.py tests/test_proxies_api.py
git commit -m "feat: extend update proxy endpoint with scheme, status, and validation"
```

---

### Task 2: Frontend — Add updateProxy API function

**Files:**
- Modify: `frontend/src/api/proxies.ts`

**Interfaces:**
- Consumes: `client` from `./client`, `ProxyItem` type already defined in same file
- Produces: `updateProxy(id: number, data: UpdateProxyData): Promise<ProxyItem>` — used by `EditProxyDialog` in Task 3

- [ ] **Step 1: Add updateProxy function**

Append before the closing of the file in `frontend/src/api/proxies.ts`:

```typescript
export async function updateProxy(
  id: number,
  data: {
    scheme?: string
    host?: string
    port?: number
    username?: string | null
    password?: string | null
    status?: string
  },
): Promise<ProxyItem> {
  const res = await client.put(`/api/proxies/${id}`, data)
  return res.data
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit`

Expected: No type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/proxies.ts
git commit -m "feat: add updateProxy API function"
```

---

### Task 3: Frontend — Create EditProxyDialog component

**Files:**
- Create: `frontend/src/components/proxies/EditProxyDialog.tsx`

**Interfaces:**
- Consumes: `updateProxy` from `@/api/proxies`, `ProxyItem` type from `@/api/proxies`, shadcn `Dialog`, `Field`, `Input`, `Select`, `Button`, `Spinner`, `toast` components
- Produces: `EditProxyDialog` component with props `{ proxy: ProxyItem | null, onOpenChange: (open: boolean) => void, onUpdated: () => void }` — used by `ProxiesPage` in Task 5

- [ ] **Step 1: Create EditProxyDialog.tsx**

Create `frontend/src/components/proxies/EditProxyDialog.tsx`:

```tsx
import { useEffect, useState } from 'react'
import type { ProxyItem } from '@/api/proxies'
import { updateProxy } from '@/api/proxies'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { toast } from '@/components/ui/toast'

const schemeItems = [
  { label: 'http', value: 'http' },
  { label: 'https', value: 'https' },
]

const statusItems = [
  { label: 'Alive', value: 'alive' },
  { label: 'Dead', value: 'dead' },
  { label: 'Unknown', value: 'unknown' },
]

interface Props {
  proxy: ProxyItem | null
  onOpenChange: (open: boolean) => void
  onUpdated: () => void
}

export function EditProxyDialog({ proxy, onOpenChange, onUpdated }: Props) {
  const [scheme, setScheme] = useState('http')
  const [host, setHost] = useState('')
  const [port, setPort] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [status, setStatus] = useState('unknown')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (proxy) {
      setScheme(proxy.scheme)
      setHost(proxy.host)
      setPort(String(proxy.port))
      setUsername(proxy.username ?? '')
      setPassword(proxy.password ?? '')
      setStatus(proxy.status)
      setError('')
    }
  }, [proxy])

  const handleOpenChange = (next: boolean) => {
    if (!next) setError('')
    onOpenChange(next)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!proxy) return
    setError('')
    setLoading(true)
    try {
      await updateProxy(proxy.id, {
        scheme,
        host,
        port: parseInt(port),
        username: username || null,
        password: password || null,
        status,
      })
      toast.add({ type: 'success', title: 'Proxy updated' })
      onUpdated()
      handleOpenChange(false)
    } catch (err: unknown) {
      const resp = (err as { response?: { status?: number; data?: { detail?: string } } })
        ?.response
      if (resp?.status === 404) {
        toast.add({ type: 'error', title: 'Proxy not found' })
        handleOpenChange(false)
      } else {
        setError(resp?.data?.detail || 'Failed to update proxy')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={proxy !== null} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Proxy</DialogTitle>
          <DialogDescription>
            Update proxy connection details and status.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <FieldGroup>
            <Field>
              <FieldLabel>Scheme</FieldLabel>
              <Select
                items={schemeItems}
                value={scheme}
                onValueChange={(value) => setScheme(value ?? 'http')}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {schemeItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <Field data-invalid={!!error}>
              <FieldLabel htmlFor="edit-proxy-host">Host</FieldLabel>
              <Input
                id="edit-proxy-host"
                placeholder="Host (e.g. 1.2.3.4)"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                aria-invalid={!!error}
                required
              />
              {error && <FieldDescription>{error}</FieldDescription>}
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-proxy-port">Port</FieldLabel>
              <Input
                id="edit-proxy-port"
                type="number"
                min={1}
                max={65535}
                placeholder="Port (e.g. 8080)"
                value={port}
                onChange={(e) => setPort(e.target.value)}
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-proxy-username">Username (optional)</FieldLabel>
              <Input
                id="edit-proxy-username"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-proxy-password">Password (optional)</FieldLabel>
              <Input
                id="edit-proxy-password"
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel>Status</FieldLabel>
              <Select
                items={statusItems}
                value={status}
                onValueChange={(value) => setStatus(value ?? 'unknown')}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {statusItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => handleOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading && <Spinner data-icon="inline-start" />}
                Save
              </Button>
            </DialogFooter>
          </FieldGroup>
        </form>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit`

Expected: No type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/proxies/EditProxyDialog.tsx
git commit -m "feat: create EditProxyDialog component"
```

---

### Task 4: Frontend — Add Edit icon to ProxyTable and wire up in ProxiesPage

**Files:**
- Modify: `frontend/src/components/proxies/ProxyTable.tsx`
- Modify: `frontend/src/pages/ProxiesPage.tsx`

**Interfaces:**
- Consumes: `EditProxyDialog` from Task 3, `ProxyItem` type, `PencilIcon` from lucide-react
- Produces: Complete edit flow — icon click → dialog open → save → table refreshes

- [ ] **Step 1: Add onEdit prop and PencilIcon to ProxyTable**

In `frontend/src/components/proxies/ProxyTable.tsx`, update the import:

```tsx
import { PencilIcon, Trash2Icon } from 'lucide-react'
```

Update the `Props` interface:

```tsx
interface Props {
  proxies: ProxyItem[]
  selected: Set<number>
  onToggleSelect: (id: number) => void
  onToggleSelectAll: () => void
  onEdit: (proxy: ProxyItem) => void
  onDelete: (id: number) => void
}
```

Update the destructured props:

```tsx
export function ProxyTable({
  proxies,
  selected,
  onToggleSelect,
  onToggleSelectAll,
  onEdit,
  onDelete,
}: Props) {
```

In the table row actions cell (the last `<TableCell>` inside the `.map()`), add the Edit button before the Delete button:

```tsx
              <TableCell>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    onClick={() => onEdit(proxy)}
                    aria-label={`Edit ${proxy.host}:${proxy.port}`}
                  >
                    <PencilIcon />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    onClick={() => onDelete(proxy.id)}
                    aria-label={`Delete ${proxy.host}:${proxy.port}`}
                  >
                    <Trash2Icon />
                  </Button>
                </div>
              </TableCell>
```

- [ ] **Step 2: Wire up EditProxyDialog in ProxiesPage**

In `frontend/src/pages/ProxiesPage.tsx`, add the import:

```tsx
import { EditProxyDialog } from '@/components/proxies/EditProxyDialog'
```

Add the `ProxyItem` type import (update the existing import from `@/api/proxies`):

```tsx
import {
  clearDeadProxies,
  deleteManyProxies,
  deleteProxy,
  fetchProxies,
  triggerCheckAll,
  type ProxyItem,
  type StatsSummary,
} from '@/api/proxies'
```

Add state after the existing `showForm` state:

```tsx
const [editingProxy, setEditingProxy] = useState<ProxyItem | null>(null)
```

Add `onEdit` prop to `ProxyTable`:

```tsx
          <ProxyTable
            proxies={data.items}
            selected={selected}
            onToggleSelect={toggleSelect}
            onToggleSelectAll={toggleSelectAll}
            onEdit={setEditingProxy}
            onDelete={handleDelete}
          />
```

Add `EditProxyDialog` after the existing `AddProxyDialog` at the bottom of the JSX:

```tsx
      <EditProxyDialog
        proxy={editingProxy}
        onOpenChange={() => setEditingProxy(null)}
        onUpdated={invalidate}
      />
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit`

Expected: No type errors.

- [ ] **Step 4: Verify lint**

Run: `cd frontend && npm run lint`

Expected: No new errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/proxies/ProxyTable.tsx frontend/src/pages/ProxiesPage.tsx
git commit -m "feat: wire up edit proxy flow with icon and dialog"
```
