import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import LogsPage from '../pages/LogsPage'
import * as logsApi from '../api/logs'
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
vi.mock('../api/logs')

function logEvent(id: number, tenantId = 1): RealtimeEvent {
  return {
    topic: 'logs',
    data: {
      id,
      tenant_id: tenantId,
      created_at: '2026-01-01T00:00:00Z',
      method: 'GET',
      host: 'example.com',
      path: '/',
      client_ip: '10.0.0.1',
      auth_status: 'allowed',
      proxy_host: '1.1.1.1',
      proxy_port: 80,
      response_bytes: 10,
    } as unknown as Record<string, unknown>,
  }
}

function renderPage(filters?: Record<string, unknown>) {
  localStorage.setItem('access_token', 'fake-token')
  localStorage.setItem('selected_tenant_id', '1')
  if (filters) {
    localStorage.setItem('proxyhub-logs-filters', JSON.stringify(filters))
  }
  vi.spyOn(authApi, 'getMe').mockResolvedValue({
    id: 1, username: 'admin', is_admin: true, email: null,
  })
  vi.spyOn(tenantsApi, 'listTenants').mockResolvedValue([
    { id: 1, name: 'Default', slug: 'default', created_at: '2026-01-01T00:00:00' },
  ])
  vi.mocked(logsApi.fetchLogs).mockResolvedValue({
    items: [], total: 0, page: 1, size: 20,
  })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const spy = vi.spyOn(queryClient, 'invalidateQueries')
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <TenantProvider>
        <BrowserRouter>
          <LogsPage />
        </BrowserRouter>
      </TenantProvider>
    </QueryClientProvider>
  )
  return { ...utils, invalidateSpy: spy }
}

describe('LogsPage realtime handling', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('coalesces invalidations while a filtered view is shown', async () => {
    // Any filter makes `liveRef` false, so events refetch instead of being
    // prepended.
    const { invalidateSpy } = renderPage({ pageSize: 20, method: 'POST', search: '' })
    await waitFor(() => expect(listener).toBeDefined())
    await screen.findByText('No requests found')

    vi.useFakeTimers()
    invalidateSpy.mockClear()
    for (let i = 0; i < 5; i += 1) listener?.(logEvent(i))

    // Five requests in the same second must not mean five refetches.
    expect(invalidateSpy).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1000)
    expect(invalidateSpy).toHaveBeenCalledTimes(1)
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['logs'] })
  })

  it('cancels the pending flush when the page unmounts', async () => {
    const { unmount } = renderPage()
    await waitFor(() => expect(listener).toBeDefined())
    await screen.findByText('No requests found')

    // Real timers: spying on setTimeout while vitest's fake clock is installed
    // leaves the fake wrapper on `globalThis` after it is restored, and every
    // later `waitFor` hangs. The flush is a 0ms timer and nothing below yields,
    // so the real clock is enough.
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout')
    const clearSpy = vi.spyOn(globalThis, 'clearTimeout')

    listener?.(logEvent(1))
    // The subscription schedules exactly one flush for the buffered event.
    const flushHandle = setTimeoutSpy.mock.results.at(-1)?.value
    expect(flushHandle).toBeDefined()

    unmount()

    // Without the cleanup the timer would survive the unmount and call
    // setState on a component that no longer exists.
    expect(clearSpy).toHaveBeenCalledWith(flushHandle)
  })

  it('does not prepend another tenant\'s log', async () => {
    renderPage()
    await waitFor(() => expect(listener).toBeDefined())
    await screen.findByText('No requests found')

    // The flush is a 0ms timer, so wait on the DOM rather than on a clock:
    // fake timers here would leak a pending timer into the next test.
    listener?.(logEvent(1, 2))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(screen.queryByText(/example\.com/)).not.toBeInTheDocument()

    listener?.(logEvent(2, 1))
    expect(await screen.findByText(/example\.com/)).toBeInTheDocument()
  })

  it('refetches instead of prepending when no tenant is resolved', async () => {
    // A non-admin never loads the tenant list, so there is no id to compare
    // the event against; prepending would show another tenant's requests.
    // This test needs real timers: waitFor polls with them.
    vi.useRealTimers()
    localStorage.setItem('access_token', 'fake-token')
    localStorage.removeItem('selected_tenant_id')
    vi.spyOn(tenantsApi, 'listTenants')
    vi.spyOn(authApi, 'getMe').mockResolvedValue({
      id: 2, username: 'alice', is_admin: false, email: null,
    })
    vi.mocked(logsApi.fetchLogs).mockResolvedValue({
      items: [], total: 0, page: 1, size: 20,
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    render(
      <QueryClientProvider client={queryClient}>
        <TenantProvider>
          <BrowserRouter>
            <LogsPage />
          </BrowserRouter>
        </TenantProvider>
      </QueryClientProvider>
    )
    await waitFor(() => expect(listener).toBeDefined())
    await screen.findByText('No requests found')

    invalidateSpy.mockClear()
    listener?.(logEvent(1, 1))

    expect(screen.queryByText(/example\.com/)).not.toBeInTheDocument()
    // Real timers here: the debounce is 1s and fake timers leak between
    // tests that unmount a component with a pending timer.
    await waitFor(
      () => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['logs'] }),
      { timeout: 3000 }
    )
  })
})
