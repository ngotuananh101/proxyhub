import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import ProxiesPage from '../pages/ProxiesPage'
import * as proxiesApi from '../api/proxies'
import * as tenantsApi from '../api/tenants'
import * as authApi from '../api/auth'
import { TenantProvider } from '../lib/tenant'
import { Toaster } from '../components/ui/toast'

vi.mock('../api/proxies')
vi.mock('../hooks/useRealtime', () => ({ useRealtime: () => {} }))

const pageOne = {
  items: [
    {
      id: 1, scheme: 'http', host: '1.1.1.1', port: 80, username: null, password: null,
      status: 'alive', latency_ms: 10, last_checked_at: null,
      created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00',
    },
    {
      id: 2, scheme: 'http', host: '2.2.2.2', port: 80, username: null, password: null,
      status: 'alive', latency_ms: 10, last_checked_at: null,
      created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00',
    },
  ],
  total: 3,
  page: 1,
  size: 2,
}

const pageTwo = {
  items: [
    {
      id: 3, scheme: 'http', host: '3.3.3.3', port: 80, username: null, password: null,
      status: 'alive', latency_ms: 10, last_checked_at: null,
      created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00',
    },
  ],
  total: 3,
  page: 2,
  size: 2,
}

function renderPage() {
  localStorage.setItem('access_token', 'fake-token')
  // The selection is persisted in real use, so seed it: without it the tenant
  // id resolves one render later and the page briefly shows its skeleton.
  localStorage.setItem('selected_tenant_id', '1')
  localStorage.setItem('proxyhub-proxies-filters', JSON.stringify({
    pageSize: 2,
    statusFilter: 'all',
    search: '',
  }))
  vi.spyOn(authApi, 'getMe').mockResolvedValue({
    id: 1, username: 'admin', is_admin: true, email: null,
  })
  vi.spyOn(tenantsApi, 'listTenants').mockResolvedValue([
    { id: 1, name: 'Default', slug: 'default', created_at: '2026-01-01T00:00:00' },
  ])
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <TenantProvider>
        <BrowserRouter>
          <ProxiesPage />
        </BrowserRouter>
        <Toaster />
      </TenantProvider>
    </QueryClientProvider>
  )
}

describe('proxy bulk selection', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    vi.mocked(proxiesApi.fetchStats).mockResolvedValue({
      total: 3, alive: 3, dead: 0, unknown: 0,
    })
    vi.mocked(proxiesApi.fetchProxies).mockImplementation(async ({ page } = {}) =>
      page === 2 ? pageTwo : pageOne
    )
  })

  it('clears the selection when the page changes', async () => {
    renderPage()

    fireEvent.click(await screen.findByLabelText('Select 1.1.1.1:80'))
    expect(await screen.findByRole('button', { name: /delete \(1\)/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /next/i }))

    await screen.findByText('3.3.3.3:80')
    // The selection belonged to page 1; carrying it over would let Delete
    // remove rows the user can no longer see.
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /delete \(/i })).not.toBeInTheDocument()
    })
  })

  it('does not treat a same-sized selection on another page as all-selected', async () => {
    renderPage()

    // Select one of the two rows on page 1.
    fireEvent.click(await screen.findByLabelText('Select 1.1.1.1:80'))
    fireEvent.click(screen.getByRole('button', { name: /next/i }))

    await screen.findByText('3.3.3.3:80')
    // Page 2 has exactly one row. A stale count comparison would call the
    // header checkbox "all selected" even though row 3 is unchecked.
    const selectAll = await screen.findByLabelText('Select all proxies')
    expect(selectAll).not.toBeChecked()
  })

  it('keeps the selection and shows an error when a bulk delete fails', async () => {
    vi.mocked(proxiesApi.deleteManyProxies).mockRejectedValue(new Error('boom'))
    renderPage()

    fireEvent.click(await screen.findByLabelText('Select 1.1.1.1:80'))
    fireEvent.click(await screen.findByRole('button', { name: /delete \(1\)/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /delete \(1\)/i })).toBeInTheDocument()
    })
    expect(screen.getByText('Failed to delete selected proxies')).toBeInTheDocument()
  })
})
