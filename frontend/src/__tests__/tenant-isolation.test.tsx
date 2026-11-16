import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, MemoryRouter, Route, Routes } from 'react-router-dom'
import type { QueryKey } from '@tanstack/react-query'
import { clearSession } from '../lib/auth'
import { AdminRoute } from '../App'
import { TenantProvider } from '../lib/tenant'
import * as tenantsApi from '../api/tenants'
import * as authApi from '../api/auth'
import ProxiesPage from '../pages/ProxiesPage'
import SourcesPage from '../pages/SourcesPage'
import { fetchProxies } from '../api/proxies'

vi.mock('../api/proxies', () => ({
  fetchProxies: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 20 }),
  fetchStats: vi.fn().mockResolvedValue({ total: 0, alive: 0, dead: 0, unknown: 0 }),
  deleteProxy: vi.fn(),
  deleteManyProxies: vi.fn(),
  clearDeadProxies: vi.fn(),
  triggerCheckAll: vi.fn(),
}))

vi.mock('../api/sources', () => ({
  fetchSources: vi.fn().mockResolvedValue([]),
  deleteSource: vi.fn(),
  fetchSourceNow: vi.fn(),
  updateSource: vi.fn(),
}))

vi.mock('../hooks/useRealtime', () => ({ useRealtime: () => {} }))

const mockTenants = [
  { id: 1, name: 'Default', slug: 'default', created_at: '2026-01-01T00:00:00' },
  { id: 2, name: 'Acme Corp', slug: 'acme', created_at: '2026-01-01T00:00:00' },
]

function renderAsTenant(ui: React.ReactElement, tenantId: number) {
  localStorage.setItem('access_token', 'fake-token')
  localStorage.setItem('selected_tenant_id', String(tenantId))
  vi.spyOn(authApi, 'getMe').mockResolvedValue({
    id: 1,
    username: 'admin',
    is_admin: true,
    email: null,
  })
  vi.spyOn(tenantsApi, 'listTenants').mockResolvedValue(mockTenants)

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <TenantProvider>
        <BrowserRouter>{ui}</BrowserRouter>
      </TenantProvider>
    </QueryClientProvider>
  )
  return queryClient
}

function keysStartingWith(queryClient: QueryClient, prefix: string): QueryKey[] {
  return queryClient
    .getQueryCache()
    .getAll()
    .map((query) => query.queryKey)
    .filter((key) => Array.isArray(key) && key[0] === prefix)
}

describe('logout clears the whole session', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('clears the tenant selection along with the token', () => {
    localStorage.setItem('access_token', 't')
    localStorage.setItem('selected_tenant_id', '2')

    clearSession()

    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('selected_tenant_id')).toBeNull()
  })
})

describe('tenant-scoped query caches', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    // Module mocks keep their call history across tests by default.
    vi.mocked(fetchProxies).mockClear()
  })

  it('scopes the proxies query by the active tenant', async () => {
    const queryClient = renderAsTenant(<ProxiesPage />, 2)

    await waitFor(() => {
      const keys = keysStartingWith(queryClient, 'proxies')
      expect(keys).toContainEqual(['proxies', 2, 1, 20, 'all', ''])
    })
    // No entry is cached for another tenant. The `undefined` key is the
    // placeholder TanStack Query creates for the first render, before the
    // tenant list resolves; it is never used again once the id is known.
    const keys = keysStartingWith(queryClient, 'proxies')
    expect(keys.filter((key) => typeof key[1] === 'number').every((key) => key[1] === 2)).toBe(true)
  })

  it('scopes the stats query by the active tenant', async () => {
    const queryClient = renderAsTenant(<ProxiesPage />, 2)

    await waitFor(() => {
      expect(keysStartingWith(queryClient, 'stats')).toContainEqual(['stats', 2])
    })
  })

  it('scopes the sources query by the active tenant', async () => {
    const queryClient = renderAsTenant(<SourcesPage />, 2)

    await waitFor(() => {
      expect(keysStartingWith(queryClient, 'sources')).toContainEqual(['sources', 2])
    })
    expect(await screen.findByText('No sources yet')).toBeInTheDocument()
  })

  it('still loads a non-admin page, who never gets a tenant list', async () => {
    localStorage.setItem('access_token', 'fake-token')
    // The list endpoint is admin-only, so a member has no stored id to start
    // from. Waiting for one would leave their pages empty forever.
    vi.spyOn(authApi, 'getMe').mockResolvedValue({
      id: 2, username: 'alice', is_admin: false, email: null,
    })
    const listSpy = vi.spyOn(tenantsApi, 'listTenants')
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <TenantProvider>
          <BrowserRouter>
            <ProxiesPage />
          </BrowserRouter>
        </TenantProvider>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(vi.mocked(fetchProxies)).toHaveBeenCalled()
    })
    expect(listSpy).not.toHaveBeenCalled()
  })
})

describe('admin-only routes', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  function renderAdminRoute(isAdmin: boolean) {
    localStorage.setItem('access_token', 'fake-token')
    vi.spyOn(authApi, 'getMe').mockResolvedValue({
      id: 1,
      username: isAdmin ? 'admin' : 'alice',
      is_admin: isAdmin,
      email: null,
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/tenants']}>
          <Routes>
            <Route path="/" element={<div>home</div>} />
            <Route
              path="/tenants"
              element={
                <AdminRoute>
                  <div>tenant admin page</div>
                </AdminRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )
  }

  it('renders the page for an admin', async () => {
    renderAdminRoute(true)
    expect(await screen.findByText('tenant admin page')).toBeInTheDocument()
  })

  it('redirects a non-admin to the home page', async () => {
    renderAdminRoute(false)
    expect(await screen.findByText('home')).toBeInTheDocument()
    expect(screen.queryByText('tenant admin page')).not.toBeInTheDocument()
  })
})
