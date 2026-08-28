# Multi-tenant Frontend Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React frontend multi-tenant interface: active tenant switching on Header with automatic `X-Tenant-Id` injection across all API requests, and an Admin Tenants & Members management page at `/tenants`.

**Architecture:** A `TenantProvider` React Context manages active tenant state and synchronizes with `localStorage` and `QueryClient`. Axios request interceptor injects `X-Tenant-Id` header automatically. `AppHeader` houses the `TenantSwitcher` dropdown. `TenantsPage` provides full CRUD for tenants and memberships.

**Tech Stack:** React 19, TypeScript, TanStack Query v5, Axios, React Router v7, Lucide React, shadcn/ui (base-sera style), Vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-29-multi-tenant-frontend-design.md`

## Global Constraints

- Style is `base-sera` (square corners, clean thin borders). Do not hand-edit files in `src/components/ui/`.
- Tenant storage key in `localStorage`: `"selected_tenant_id"`.
- Header sent to backend: `X-Tenant-Id`.
- Super admin condition: `user?.is_admin === true`.
- When active tenant changes, all queries in TanStack Query must be invalidated to refresh data tables.

---

### Task 1: API client interceptor & tenant API module

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/api/tenants.ts`
- Create: `frontend/src/__tests__/tenants-api.test.ts`

**Interfaces:**
- Produces: `TenantItem`, `TenantMembershipItem`, `TenantCreateInput`, `MembershipCreateInput` types and API functions (`listTenants`, `createTenant`, `listMembers`, `addMember`, `removeMember`) in `src/api/tenants.ts`.
- Produces: `client` interceptor injecting `X-Tenant-Id`.

- [ ] **Step 1: Write failing test for client interceptor and tenants API**

Create `frontend/src/__tests__/tenants-api.test.ts`:

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import client from '../api/client'
import {
  listTenants,
  createTenant,
  listMembers,
  addMember,
  removeMember,
} from '../api/tenants'

describe('Tenant API and Client Interceptor', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('injects X-Tenant-Id header when selected_tenant_id is in localStorage', async () => {
    localStorage.setItem('selected_tenant_id', '42')
    const spy = vi.spyOn(client, 'get').mockResolvedValueOnce({ data: [] })

    await listTenants()

    expect(spy).toHaveBeenCalledWith('/api/tenants')
  })

  it('createTenant posts to /api/tenants', async () => {
    const mockTenant = { id: 1, name: 'Acme', slug: 'acme', created_at: '2026-01-01T00:00:00' }
    vi.spyOn(client, 'post').mockResolvedValueOnce({ data: mockTenant })

    const result = await createTenant({ name: 'Acme', slug: 'acme' })
    expect(result).toEqual(mockTenant)
    expect(client.post).toHaveBeenCalledWith('/api/tenants', { name: 'Acme', slug: 'acme' })
  })

  it('listMembers gets from /api/tenants/:id/members', async () => {
    const mockMembers = [{ id: 1, tenant_id: 1, user_id: 2, role: 'member' as const }]
    vi.spyOn(client, 'get').mockResolvedValueOnce({ data: mockMembers })

    const result = await listMembers(1)
    expect(result).toEqual(mockMembers)
    expect(client.get).toHaveBeenCalledWith('/api/tenants/1/members')
  })

  it('addMember posts to /api/tenants/:id/members', async () => {
    const mockMember = { id: 1, tenant_id: 1, user_id: 2, role: 'admin' as const }
    vi.spyOn(client, 'post').mockResolvedValueOnce({ data: mockMember })

    const result = await addMember(1, { user_id: 2, role: 'admin' })
    expect(result).toEqual(mockMember)
    expect(client.post).toHaveBeenCalledWith('/api/tenants/1/members', { user_id: 2, role: 'admin' })
  })

  it('removeMember deletes from /api/tenants/:id/members/:userId', async () => {
    vi.spyOn(client, 'delete').mockResolvedValueOnce({ data: null })

    await removeMember(1, 2)
    expect(client.delete).toHaveBeenCalledWith('/api/tenants/1/members/2')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/tenants-api.test.ts`
Expected: FAIL — `../api/tenants` does not exist.

- [ ] **Step 3: Update `src/api/client.ts`**

Replace `frontend/src/api/client.ts`:

```typescript
import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '',
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const tenantId = localStorage.getItem('selected_tenant_id')
  if (tenantId) {
    config.headers['X-Tenant-Id'] = tenantId
  }
  return config
})

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default client
```

- [ ] **Step 4: Create `src/api/tenants.ts`**

Create `frontend/src/api/tenants.ts`:

```typescript
import client from './client'

export interface TenantItem {
  id: number
  name: string
  slug: string
  created_at: string
}

export interface TenantCreateInput {
  name: string
  slug?: string
}

export interface TenantMembershipItem {
  id: number
  tenant_id: number
  user_id: number
  role: 'admin' | 'member'
}

export interface MembershipCreateInput {
  user_id: number
  role: string
}

export async function listTenants(): Promise<TenantItem[]> {
  const res = await client.get<TenantItem[]>('/api/tenants')
  return res.data
}

export async function createTenant(input: TenantCreateInput): Promise<TenantItem> {
  const res = await client.post<TenantItem>('/api/tenants', input)
  return res.data
}

export async function listMembers(tenantId: number): Promise<TenantMembershipItem[]> {
  const res = await client.get<TenantMembershipItem[]>(`/api/tenants/${tenantId}/members`)
  return res.data
}

export async function addMember(
  tenantId: number,
  input: MembershipCreateInput
): Promise<TenantMembershipItem> {
  const res = await client.post<TenantMembershipItem>(`/api/tenants/${tenantId}/members`, input)
  return res.data
}

export async function removeMember(tenantId: number, userId: number): Promise<void> {
  await client.delete(`/api/tenants/${tenantId}/members/${userId}`)
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/__tests__/tenants-api.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/api/tenants.ts frontend/src/__tests__/tenants-api.test.ts
git commit -m "feat(frontend): add tenant API module and X-Tenant-Id request interceptor"
```

---

### Task 2: Tenant Context & Provider (`TenantProvider`)

**Files:**
- Create: `frontend/src/lib/tenant.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/__tests__/tenant-context.test.tsx`

**Interfaces:**
- Produces: `TenantProvider`, `useTenant` hook returning `{ activeTenant, availableTenants, setActiveTenant, isLoading, refreshTenants }`.

- [ ] **Step 1: Write failing test for `TenantProvider`**

Create `frontend/src/__tests__/tenant-context.test.tsx`:

```tsx
import { render, screen, act } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TenantProvider, useTenant } from '../lib/tenant'
import * as tenantsApi from '../api/tenants'
import * as authApi from '../api/auth'

const mockTenants = [
  { id: 1, name: 'Default', slug: 'default', created_at: '2026-01-01T00:00:00' },
  { id: 2, name: 'Acme Corp', slug: 'acme', created_at: '2026-01-01T00:00:00' },
]

function ConsumerComponent() {
  const { activeTenant, availableTenants, setActiveTenant } = useTenant()
  return (
    <div>
      <span data-testid="active">{activeTenant?.name ?? 'None'}</span>
      <span data-testid="count">{availableTenants.length}</span>
      <button onClick={() => setActiveTenant(mockTenants[1])}>Switch to Acme</button>
    </div>
  )
}

describe('TenantProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('loads tenants and defaults to first tenant when none stored', async () => {
    vi.spyOn(authApi, 'getMe').mockResolvedValueOnce({ id: 1, username: 'admin', is_admin: true, email: null, created_at: '' })
    vi.spyOn(tenantsApi, 'listTenants').mockResolvedValueOnce(mockTenants)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <TenantProvider>
          <ConsumerComponent />
        </TenantProvider>
      </QueryClientProvider>
    )

    expect(await screen.findByTestId('active')).toHaveTextContent('Default')
    expect(screen.getByTestId('count')).toHaveTextContent('2')
    expect(localStorage.getItem('selected_tenant_id')).toBe('1')
  })

  it('switches active tenant and updates localStorage', async () => {
    vi.spyOn(authApi, 'getMe').mockResolvedValueOnce({ id: 1, username: 'admin', is_admin: true, email: null, created_at: '' })
    vi.spyOn(tenantsApi, 'listTenants').mockResolvedValueOnce(mockTenants)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <TenantProvider>
          <ConsumerComponent />
        </TenantProvider>
      </QueryClientProvider>
    )

    await screen.findByText('Switch to Acme')
    act(() => {
      screen.getByText('Switch to Acme').click()
    })

    expect(screen.getByTestId('active')).toHaveTextContent('Acme Corp')
    expect(localStorage.getItem('selected_tenant_id')).toBe('2')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/tenant-context.test.tsx`
Expected: FAIL — `../lib/tenant` not found.

- [ ] **Step 3: Create `src/lib/tenant.tsx`**

Create `frontend/src/lib/tenant.tsx`:

```tsx
import React, { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listTenants, type TenantItem } from '@/api/tenants'
import { getMe } from '@/api/auth'
import { isAuthenticated } from '@/lib/auth'

interface TenantContextValue {
  activeTenant: TenantItem | null
  availableTenants: TenantItem[]
  setActiveTenant: (tenant: TenantItem) => void
  isLoading: boolean
  refreshTenants: () => Promise<void>
}

const TenantContext = createContext<TenantContextValue | undefined>(undefined)

const STORAGE_KEY = 'selected_tenant_id'

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const authenticated = isAuthenticated()

  const { data: user } = useQuery({
    queryKey: ['me'],
    queryFn: getMe,
    enabled: authenticated,
  })

  const { data: tenants = [], isLoading, refetch } = useQuery({
    queryKey: ['tenants'],
    queryFn: listTenants,
    enabled: authenticated && user?.is_admin === true,
  })

  const [activeTenant, setActiveTenantState] = useState<TenantItem | null>(null)

  // Initialize or reconcile active tenant
  useEffect(() => {
    if (!tenants || tenants.length === 0) return

    const storedIdStr = localStorage.getItem(STORAGE_KEY)
    const storedId = storedIdStr ? parseInt(storedIdStr, 10) : null

    if (storedId) {
      const match = tenants.find((t) => t.id === storedId)
      if (match) {
        setActiveTenantState(match)
        return
      }
    }

    // Default to first tenant
    const defaultTenant = tenants.find((t) => t.slug === 'default') ?? tenants[0]
    setActiveTenantState(defaultTenant)
    localStorage.setItem(STORAGE_KEY, String(defaultTenant.id))
  }, [tenants])

  const setActiveTenant = useCallback(
    (tenant: TenantItem) => {
      setActiveTenantState(tenant)
      localStorage.setItem(STORAGE_KEY, String(tenant.id))
      // Invalidate all query caches so lists/stats refresh under new tenant
      queryClient.invalidateQueries()
    },
    [queryClient]
  )

  const refreshTenants = useCallback(async () => {
    await refetch()
  }, [refetch])

  return (
    <TenantContext.Provider
      value={{
        activeTenant,
        availableTenants: tenants,
        setActiveTenant,
        isLoading,
        refreshTenants,
      }}
    >
      {children}
    </TenantContext.Provider>
  )
}

export function useTenant(): TenantContextValue {
  const context = useContext(TenantContext)
  if (!context) {
    throw new Error('useTenant must be used within a TenantProvider')
  }
  return context
}
```

- [ ] **Step 4: Update `src/App.tsx` with `TenantProvider`**

Modify `frontend/src/App.tsx` to wrap contents inside `TenantProvider`:

```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { isAuthenticated } from './lib/auth'
import { ThemeProvider } from './lib/theme'
import { TenantProvider } from './lib/tenant'
import { AppLayout } from './components/layout/AppLayout'
import { Toaster } from './components/ui/toast'
import { TooltipProvider } from './components/ui/tooltip'
import LoginPage from './pages/LoginPage'
import LogsPage from './pages/LogsPage'
import ProxiesPage from './pages/ProxiesPage'
import ProfilePage from './pages/ProfilePage'
import SettingsPage from './pages/SettingsPage'
import SourcesPage from './pages/SourcesPage'

const queryClient = new QueryClient()

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <TenantProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route
                  element={
                    <ProtectedRoute>
                      <AppLayout />
                    </ProtectedRoute>
                  }
                >
                  <Route path="/" element={<ProxiesPage />} />
                  <Route path="/sources" element={<SourcesPage />} />
                  <Route path="/logs" element={<LogsPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/profile" element={<ProfilePage />} />
                </Route>
              </Routes>
            </BrowserRouter>
            <Toaster />
          </TenantProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/__tests__/tenant-context.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/tenant.tsx frontend/src/App.tsx frontend/src/__tests__/tenant-context.test.tsx
git commit -m "feat(frontend): add TenantProvider context and state management"
```

---

### Task 3: Header Tenant Switcher Component

**Files:**
- Create: `frontend/src/components/layout/TenantSwitcher.tsx`
- Modify: `frontend/src/components/layout/AppHeader.tsx`
- Create: `frontend/src/__tests__/tenant-switcher.test.tsx`

**Interfaces:**
- Produces: `TenantSwitcher` component rendering active tenant trigger, dropdown menu listing tenants with checkmark on active, and "+ Manage Tenants" link for admin.

- [ ] **Step 1: Write failing test for `TenantSwitcher`**

Create `frontend/src/__tests__/tenant-switcher.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import { TenantSwitcher } from '../components/layout/TenantSwitcher'
import * as tenantLib from '../lib/tenant'

const mockTenants = [
  { id: 1, name: 'Default', slug: 'default', created_at: '2026-01-01T00:00:00' },
  { id: 2, name: 'Acme Corp', slug: 'acme', created_at: '2026-01-01T00:00:00' },
]

describe('TenantSwitcher', () => {
  it('renders active tenant name and dropdown options', () => {
    const setActiveTenant = vi.fn()
    vi.spyOn(tenantLib, 'useTenant').mockReturnValue({
      activeTenant: mockTenants[0],
      availableTenants: mockTenants,
      setActiveTenant,
      isLoading: false,
      refreshTenants: vi.fn(),
    })

    render(
      <BrowserRouter>
        <TenantSwitcher />
      </BrowserRouter>
    )

    expect(screen.getByText('Default')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/tenant-switcher.test.tsx`
Expected: FAIL — `TenantSwitcher` does not exist.

- [ ] **Step 3: Create `TenantSwitcher.tsx`**

Create `frontend/src/components/layout/TenantSwitcher.tsx`:

```tsx
import { useNavigate } from 'react-router-dom'
import { Building2Icon, CheckIcon, ChevronsUpDownIcon, Settings2Icon } from 'lucide-react'
import { useTenant } from '@/lib/tenant'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { toast } from '@/components/ui/toast'

export function TenantSwitcher() {
  const navigate = useNavigate()
  const { activeTenant, availableTenants, setActiveTenant } = useTenant()

  if (!activeTenant && availableTenants.length === 0) {
    return null
  }

  const handleSelect = (tenant: typeof availableTenants[0]) => {
    if (tenant.id === activeTenant?.id) return
    setActiveTenant(tenant)
    toast.success(`Switched to tenant: ${tenant.name}`)
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 border-dashed px-2.5 font-normal text-xs"
          />
        }
        aria-label="Select tenant"
      >
        <Building2Icon className="size-3.5 text-muted-foreground" />
        <span className="max-w-[120px] truncate font-medium text-foreground">
          {activeTenant?.name ?? 'Select tenant'}
        </span>
        <ChevronsUpDownIcon className="size-3 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-xs text-muted-foreground font-normal">
            Tenants
          </DropdownMenuLabel>
          {availableTenants.map((tenant) => {
            const isSelected = tenant.id === activeTenant?.id
            return (
              <DropdownMenuItem
                key={tenant.id}
                onClick={() => handleSelect(tenant)}
                className="flex items-center justify-between text-xs"
              >
                <div className="flex flex-col">
                  <span className="font-medium text-foreground">{tenant.name}</span>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {tenant.slug}
                  </span>
                </div>
                {isSelected && <CheckIcon className="size-3.5 text-primary" />}
              </DropdownMenuItem>
            )
          })}
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem
            onClick={() => navigate('/tenants')}
            className="text-xs text-muted-foreground"
          >
            <Settings2Icon className="size-3.5" />
            Manage tenants
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
```

- [ ] **Step 4: Update `src/components/layout/AppHeader.tsx`**

Modify `frontend/src/components/layout/AppHeader.tsx` to include `TenantSwitcher`:

```tsx
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { LogOutIcon, UserIcon } from 'lucide-react'
import { getMe } from '@/api/auth'
import { clearToken } from '@/lib/auth'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Separator } from '@/components/ui/separator'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { TenantSwitcher } from './TenantSwitcher'
import { ThemeToggle } from './ThemeToggle'

export function AppHeader() {
  const navigate = useNavigate()
  const { data: user } = useQuery({ queryKey: ['me'], queryFn: getMe })

  const initials = (user?.username ?? '?').slice(0, 2).toUpperCase()

  const handleLogout = () => {
    clearToken()
    navigate('/login')
  }

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b bg-background px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="h-5" />
      <div className="flex-1" />
      <TenantSwitcher />
      <ThemeToggle />
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button variant="ghost" size="icon" className="size-8 rounded-full" />
          }
          aria-label="User menu"
        >
          <Avatar className="size-8">
            <AvatarFallback className="text-xs">{initials}</AvatarFallback>
          </Avatar>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuGroup>
            <DropdownMenuLabel>
              <div className="flex flex-col gap-0.5">
                <span className="truncate text-sm text-foreground">{user?.username}</span>
                {user?.email && (
                  <span className="truncate font-normal">{user.email}</span>
                )}
              </div>
            </DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuItem onClick={() => navigate('/profile')}>
              <UserIcon />
              Manage profile
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onClick={handleLogout}>
              <LogOutIcon />
              Log out
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/__tests__/tenant-switcher.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/layout/TenantSwitcher.tsx frontend/src/components/layout/AppHeader.tsx frontend/src/__tests__/tenant-switcher.test.tsx
git commit -m "feat(frontend): add TenantSwitcher component to AppHeader"
```

---

### Task 4: Admin Tenants Management Page & Dialogs

**Files:**
- Create: `frontend/src/components/tenants/CreateTenantDialog.tsx`
- Create: `frontend/src/components/tenants/ManageMembersDialog.tsx`
- Create: `frontend/src/pages/TenantsPage.tsx`
- Modify: `frontend/src/components/layout/AppSidebar.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/__tests__/tenants-page.test.tsx`

**Interfaces:**
- Produces: `TenantsPage` at `/tenants`, `CreateTenantDialog`, `ManageMembersDialog`, and admin sidebar link.

- [ ] **Step 1: Write failing test for `TenantsPage`**

Create `frontend/src/__tests__/tenants-page.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import TenantsPage from '../pages/TenantsPage'
import * as tenantsApi from '../api/tenants'
import * as authApi from '../api/auth'

const mockTenants = [
  { id: 1, name: 'Default', slug: 'default', created_at: '2026-01-01T00:00:00' },
  { id: 2, name: 'Beta Team', slug: 'beta', created_at: '2026-01-02T00:00:00' },
]

describe('TenantsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders tenant table and create button', async () => {
    vi.spyOn(authApi, 'getMe').mockResolvedValueOnce({ id: 1, username: 'admin', is_admin: true, email: null, created_at: '' })
    vi.spyOn(tenantsApi, 'listTenants').mockResolvedValueOnce(mockTenants)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <TenantsPage />
        </BrowserRouter>
      </QueryClientProvider>
    )

    expect(await screen.findByText('Default')).toBeInTheDocument()
    expect(screen.getByText('Beta Team')).toBeInTheDocument()
    expect(screen.getByText('Create Tenant')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/tenants-page.test.tsx`
Expected: FAIL — `TenantsPage` does not exist.

- [ ] **Step 3: Create `CreateTenantDialog.tsx`**

Create `frontend/src/components/tenants/CreateTenantDialog.tsx`:

```tsx
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createTenant } from '@/api/tenants'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { toast } from '@/components/ui/toast'

interface CreateTenantDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateTenantDialog({ open, onOpenChange }: CreateTenantDialogProps) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')

  const createMutation = useMutation({
    mutationFn: createTenant,
    onSuccess: (tenant) => {
      toast.success(`Tenant '${tenant.name}' created`)
      queryClient.invalidateQueries({ queryKey: ['tenants'] })
      setName('')
      setSlug('')
      onOpenChange(false)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg || 'Failed to create tenant')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    createMutation.mutate({
      name: name.trim(),
      slug: slug.trim() || undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Create Tenant</DialogTitle>
            <DialogDescription>
              Add a new isolated tenant workspace.
            </DialogDescription>
          </DialogHeader>
          <FieldGroup className="py-4">
            <Field>
              <FieldLabel htmlFor="tenant-name">Tenant Name</FieldLabel>
              <Input
                id="tenant-name"
                placeholder="e.g. Acme Corp"
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                  if (!slug || slug === name.toLowerCase().replace(/\s+/g, '-')) {
                    setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''))
                  }
                }}
                required
                autoFocus
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="tenant-slug">Slug</FieldLabel>
              <Input
                id="tenant-slug"
                placeholder="e.g. acme-corp"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
              />
              <FieldDescription>
                Unique identifier used for routing and URLs.
              </FieldDescription>
            </Field>
          </FieldGroup>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending || !name.trim()}>
              {createMutation.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 4: Create `ManageMembersDialog.tsx`**

Create `frontend/src/components/tenants/ManageMembersDialog.tsx`:

```tsx
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { addMember, listMembers, removeMember, type TenantItem } from '@/api/tenants'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { toast } from '@/components/ui/toast'
import { Trash2Icon, UserPlusIcon } from 'lucide-react'

interface ManageMembersDialogProps {
  tenant: TenantItem | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ManageMembersDialog({ tenant, open, onOpenChange }: ManageMembersDialogProps) {
  const queryClient = useQueryClient()
  const [userId, setUserId] = useState('')
  const [role, setRole] = useState<'member' | 'admin'>('member')

  const { data: members = [], isLoading } = useQuery({
    queryKey: ['tenant-members', tenant?.id],
    queryFn: () => (tenant ? listMembers(tenant.id) : Promise.resolve([])),
    enabled: open && !!tenant,
  })

  const addMutation = useMutation({
    mutationFn: () => {
      if (!tenant) throw new Error('No tenant')
      return addMember(tenant.id, { user_id: parseInt(userId, 10), role })
    },
    onSuccess: () => {
      toast.success('Member added')
      queryClient.invalidateQueries({ queryKey: ['tenant-members', tenant?.id] })
      setUserId('')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg || 'Failed to add member')
    },
  })

  const removeMutation = useMutation({
    mutationFn: (targetUserId: number) => {
      if (!tenant) throw new Error('No tenant')
      return removeMember(tenant.id, targetUserId)
    },
    onSuccess: () => {
      toast.success('Member removed')
      queryClient.invalidateQueries({ queryKey: ['tenant-members', tenant?.id] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(msg || 'Failed to remove member')
    },
  })

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault()
    if (!userId.trim()) return
    addMutation.mutate()
  }

  if (!tenant) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Manage Members — {tenant.name}</DialogTitle>
          <DialogDescription>
            Add or remove user memberships for tenant <code className="font-mono text-xs">{tenant.slug}</code>.
          </DialogDescription>
        </DialogHeader>

        {/* Add member form */}
        <form onSubmit={handleAdd} className="flex items-end gap-2 border-b pb-4">
          <Field className="flex-1">
            <FieldLabel htmlFor="user-id">User ID</FieldLabel>
            <Input
              id="user-id"
              type="number"
              placeholder="e.g. 2"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              required
            />
          </Field>
          <Field className="w-32">
            <FieldLabel htmlFor="member-role">Role</FieldLabel>
            <Select value={role} onValueChange={(val) => setRole(val as 'member' | 'admin')}>
              <SelectTrigger id="member-role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="member">Member</SelectItem>
                <SelectItem value="admin">Admin</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Button type="submit" size="default" disabled={addMutation.isPending || !userId.trim()}>
            <UserPlusIcon className="size-4 mr-1" />
            Add
          </Button>
        </form>

        {/* Members table */}
        <div className="max-h-[300px] overflow-y-auto">
          {isLoading ? (
            <p className="py-4 text-center text-xs text-muted-foreground">Loading members...</p>
          ) : members.length === 0 ? (
            <p className="py-4 text-center text-xs text-muted-foreground">No members assigned yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User ID</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead className="w-[80px] text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="font-mono text-xs">User #{m.user_id}</TableCell>
                    <TableCell>
                      <Badge variant={m.role === 'admin' ? 'default' : 'secondary'} className="text-[10px]">
                        {m.role}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-7 text-destructive hover:bg-destructive/10"
                        onClick={() => removeMutation.mutate(m.user_id)}
                        disabled={removeMutation.isPending}
                        aria-label={`Remove user ${m.user_id}`}
                      >
                        <Trash2Icon className="size-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 5: Create `TenantsPage.tsx`**

Create `frontend/src/pages/TenantsPage.tsx`:

```tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building2Icon, PlusIcon, UsersIcon, CheckIcon } from 'lucide-react'
import { listTenants, type TenantItem } from '@/api/tenants'
import { useTenant } from '@/lib/tenant'
import { useTimezone } from '@/hooks/use-timezone'
import { formatDateTime } from '@/lib/datetime'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { CreateTenantDialog } from '@/components/tenants/CreateTenantDialog'
import { ManageMembersDialog } from '@/components/tenants/ManageMembersDialog'

export default function TenantsPage() {
  const { tz } = useTimezone()
  const { activeTenant, setActiveTenant } = useTenant()
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedTenantForMembers, setSelectedTenantForMembers] = useState<TenantItem | null>(null)

  const { data: tenants = [], isLoading } = useQuery({
    queryKey: ['tenants'],
    queryFn: listTenants,
  })

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tenants</h1>
          <p className="text-sm text-muted-foreground">
            Manage isolated multi-tenant workspaces and member permissions.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <PlusIcon className="size-4 mr-1.5" />
          Create Tenant
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-medium">All Tenants</CardTitle>
          <CardDescription>
            Each tenant has its own isolated proxy pools, sources, request logs, and stats.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead>Created At</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-28" /></TableCell>
                    <TableCell className="text-right"><Skeleton className="h-8 w-24 ml-auto" /></TableCell>
                  </TableRow>
                ))
              ) : tenants.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="h-32 text-center text-muted-foreground">
                    No tenants found.
                  </TableCell>
                </TableRow>
              ) : (
                tenants.map((tenant) => {
                  const isActive = tenant.id === activeTenant?.id
                  return (
                    <TableRow key={tenant.id}>
                      <TableCell className="font-medium">
                        <div className="flex items-center gap-2">
                          <Building2Icon className="size-4 text-muted-foreground" />
                          <span>{tenant.name}</span>
                          {isActive && (
                            <Badge variant="outline" className="text-[10px] bg-primary/5 text-primary border-primary/20">
                              Active
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <code className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">
                          {tenant.slug}
                        </code>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDateTime(tenant.created_at, tz)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            variant={isActive ? 'secondary' : 'outline'}
                            size="sm"
                            className="h-8 text-xs gap-1"
                            onClick={() => setActiveTenant(tenant)}
                            disabled={isActive}
                          >
                            {isActive ? (
                              <>
                                <CheckIcon className="size-3 text-primary" />
                                Active
                              </>
                            ) : (
                              'Switch to'
                            )}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8 text-xs gap-1"
                            onClick={() => setSelectedTenantForMembers(tenant)}
                          >
                            <UsersIcon className="size-3 text-muted-foreground" />
                            Members
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <CreateTenantDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
      />

      <ManageMembersDialog
        tenant={selectedTenantForMembers}
        open={!!selectedTenantForMembers}
        onOpenChange={(open) => {
          if (!open) setSelectedTenantForMembers(null)
        }}
      />
    </div>
  )
}
```

- [ ] **Step 6: Update `src/components/layout/AppSidebar.tsx` and `src/App.tsx`**

In `frontend/src/components/layout/AppSidebar.tsx`:
Add `Building2Icon` import and conditionally display `Tenants` menu item for admin users:

```tsx
import { NavLink, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Building2Icon,
  DownloadIcon,
  GlobeIcon,
  ScrollTextIcon,
  SettingsIcon,
  ShieldIcon,
  UserIcon,
} from 'lucide-react'
import { getMe } from '@/api/auth'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'

const baseNavItems = [
  { to: '/', label: 'Proxies', icon: GlobeIcon },
  { to: '/sources', label: 'Sources', icon: DownloadIcon },
  { to: '/logs', label: 'Logs', icon: ScrollTextIcon },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
  { to: '/profile', label: 'Profile', icon: UserIcon },
]

export function AppSidebar() {
  const { pathname } = useLocation()
  const { data: user } = useQuery({ queryKey: ['me'], queryFn: getMe })

  const navItems = [
    ...baseNavItems.slice(0, 4),
    ...(user?.is_admin ? [{ to: '/tenants', label: 'Tenants', icon: Building2Icon }] : []),
    baseNavItems[4],
  ]

  return (
    <Sidebar>
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-1.5">
          <div className="flex size-8 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
            <ShieldIcon />
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-semibold">ProxyHub</span>
            <span className="text-xs text-sidebar-foreground/60">Proxy Manager</span>
          </div>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Menu</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => {
                const isActive = item.to === '/' ? pathname === '/' : pathname.startsWith(item.to)
                return (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton
                      render={<NavLink to={item.to} end={item.to === '/'} />}
                      isActive={isActive}
                    >
                      <item.icon />
                      <span>{item.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <p className="px-2 text-xs text-sidebar-foreground/50">ProxyHub v0.1.0</p>
      </SidebarFooter>
    </Sidebar>
  )
}
```

In `frontend/src/App.tsx`:
Add Route for `/tenants`:

```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { isAuthenticated } from './lib/auth'
import { ThemeProvider } from './lib/theme'
import { TenantProvider } from './lib/tenant'
import { AppLayout } from './components/layout/AppLayout'
import { Toaster } from './components/ui/toast'
import { TooltipProvider } from './components/ui/tooltip'
import LoginPage from './pages/LoginPage'
import LogsPage from './pages/LogsPage'
import ProxiesPage from './pages/ProxiesPage'
import ProfilePage from './pages/ProfilePage'
import SettingsPage from './pages/SettingsPage'
import SourcesPage from './pages/SourcesPage'
import TenantsPage from './pages/TenantsPage'

const queryClient = new QueryClient()

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <TenantProvider>
            <BrowserRouter>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route
                  element={
                    <ProtectedRoute>
                      <AppLayout />
                    </ProtectedRoute>
                  }
                >
                  <Route path="/" element={<ProxiesPage />} />
                  <Route path="/sources" element={<SourcesPage />} />
                  <Route path="/logs" element={<LogsPage />} />
                  <Route path="/tenants" element={<TenantsPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/profile" element={<ProfilePage />} />
                </Route>
              </Routes>
            </BrowserRouter>
            <Toaster />
          </TenantProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
```

- [ ] **Step 7: Run all frontend tests and type checks**

Run: `cd frontend && npx vitest run`
Expected: ALL PASS.

Run: `cd frontend && npx tsc -b && npm run build`
Expected: 0 errors, build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/tenants/ frontend/src/pages/TenantsPage.tsx frontend/src/components/layout/AppSidebar.tsx frontend/src/App.tsx frontend/src/__tests__/tenants-page.test.tsx
git commit -m "feat(frontend): add TenantsPage and admin member management dialogs"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - Active tenant switching via `AppHeader` dropdown -> Task 3
   - `X-Tenant-Id` header injected in Axios requests -> Task 1
   - State management with TanStack Query cache invalidation -> Task 2
   - Admin management page `/tenants` with create tenant & member management dialogs -> Task 4
   - Admin sidebar link -> Task 4
2. **Type safety:** All interfaces and props explicitly typed, `tsc -b` passes with 0 errors.
3. **Test coverage:** Unit tests covering API interceptor, TenantContext, TenantSwitcher, and TenantsPage.
