import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import ProxiesPage from '../pages/ProxiesPage'
import * as proxiesApi from '../api/proxies'
import * as tenantsApi from '../api/tenants'
import * as authApi from '../api/auth'
import { TenantProvider } from '../lib/tenant'
import type { RealtimeEvent } from '../hooks/useRealtime'

// Capture the page's subscription so the tests can drive it directly.
let listener: ((event: RealtimeEvent) => void) | undefined
vi.mock('../hooks/useRealtime', () => ({
  useRealtime: (onEvent: (event: RealtimeEvent) => void) => {
    listener = onEvent
  },
}))
vi.mock('../api/proxies')

function statsEvent(tenantId: number | null): RealtimeEvent {
  return {
    topic: 'stats',
    data: { tenant_id: tenantId, total: 3, alive: 2, dead: 1, unknown: 0 },
  }
}

async function renderPage() {
  localStorage.setItem('access_token', 'fake-token')
  localStorage.setItem('selected_tenant_id', '1')
  vi.spyOn(authApi, 'getMe').mockResolvedValue({
    id: 1, username: 'admin', is_admin: true, email: null,
  })
  vi.spyOn(tenantsApi, 'listTenants').mockResolvedValue([
    { id: 1, name: 'Default', slug: 'default', created_at: '2026-01-01T00:00:00' },
    { id: 2, name: 'Acme', slug: 'acme', created_at: '2026-01-01T00:00:00' },
  ])
  vi.mocked(proxiesApi.fetchProxies).mockResolvedValue({
    items: [], total: 0, page: 1, size: 20,
  })
  vi.mocked(proxiesApi.fetchStats).mockResolvedValue({
    total: 3, alive: 2, dead: 1, unknown: 0,
  })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const spy = vi.spyOn(queryClient, 'invalidateQueries')
  render(
    <QueryClientProvider client={queryClient}>
      <TenantProvider>
        <BrowserRouter>
          <ProxiesPage />
        </BrowserRouter>
      </TenantProvider>
    </QueryClientProvider>
  )
  await screen.findByText('Total proxies')
  return spy
}

describe('ProxiesPage realtime stats handling', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('refetches when the active tenant’s stats change', async () => {
    const invalidateSpy = await renderPage()
    await waitFor(() => expect(listener).toBeDefined())
    invalidateSpy.mockClear()

    listener?.(statsEvent(1))

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['stats'] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['proxies'] })
  })

  it('ignores another tenant’s stats event', async () => {
    const invalidateSpy = await renderPage()
    await waitFor(() => expect(listener).toBeDefined())
    invalidateSpy.mockClear()

    // The server already scopes the feed; this guards against refetching the
    // whole table every time some other tenant's health check finishes.
    listener?.(statsEvent(2))

    expect(invalidateSpy).not.toHaveBeenCalled()
  })

  it('still refetches for an unscoped event', async () => {
    const invalidateSpy = await renderPage()
    await waitFor(() => expect(listener).toBeDefined())
    invalidateSpy.mockClear()

    // Legacy or pre-adoption events carry no tenant id; dropping them would
    // leave the dashboard stale.
    listener?.(statsEvent(null))

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['stats'] })
  })
})
