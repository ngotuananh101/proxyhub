import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import ProxiesPage from '../pages/ProxiesPage'
import LogsPage from '../pages/LogsPage'
import * as proxiesApi from '../api/proxies'
import * as logsApi from '../api/logs'
import { TenantProvider } from '@/lib/tenant'

vi.mock('../api/proxies')
vi.mock('../api/logs')
vi.mock('../hooks/useRealtime', () => ({ useRealtime: () => {} }))

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TenantProvider>
        <BrowserRouter>{ui}</BrowserRouter>
      </TenantProvider>
    </QueryClientProvider>,
  )
}

describe('filter persistence', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(proxiesApi.fetchProxies).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 20,
    })
    vi.mocked(logsApi.fetchLogs).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 20,
    })
  })

  it('ProxiesPage persists search + statusFilter to localStorage', async () => {
    renderWithClient(<ProxiesPage />)
    fireEvent.change(screen.getByPlaceholderText('Search host...'), {
      target: { value: 'example.com' },
    })

    await waitFor(() => {
      const raw = localStorage.getItem('proxyhub-proxies-filters')
      expect(raw).toContain('example.com')
    })
  })

  it('ProxiesPage Clear filters button resets search and status', async () => {
    localStorage.setItem(
      'proxyhub-proxies-filters',
      JSON.stringify({ pageSize: 20, statusFilter: 'dead', search: 'foo' }),
    )
    renderWithClient(<ProxiesPage />)

    const clearBtn = await screen.findByRole('button', { name: /clear filters/i })
    expect(clearBtn).toBeEnabled()
    fireEvent.click(clearBtn)

    await waitFor(() => {
      const raw = localStorage.getItem('proxyhub-proxies-filters')
      expect(raw).toContain('"statusFilter":"all"')
      expect(raw).toContain('"search":""')
    })
  })

  it('LogsPage persists filters and restores method from localStorage', async () => {
    localStorage.setItem(
      'proxyhub-logs-filters',
      JSON.stringify({ pageSize: 20, method: 'POST', search: 'api', date: undefined }),
    )
    renderWithClient(<LogsPage />)

    await waitFor(() => {
      expect(vi.mocked(logsApi.fetchLogs)).toHaveBeenCalledWith(
        expect.objectContaining({ method: 'POST', q: 'api' }),
      )
    })
  })

  it('LogsPage Clear filters resets search and method', async () => {
    localStorage.setItem(
      'proxyhub-logs-filters',
      JSON.stringify({
        pageSize: 20,
        method: 'GET',
        search: 'host',
        date: { from: new Date().toISOString() },
      }),
    )
    renderWithClient(<LogsPage />)

    const clearBtn = await screen.findByRole('button', { name: /clear filters/i })
    expect(clearBtn).toBeEnabled()
    fireEvent.click(clearBtn)

    await waitFor(() => {
      const raw = localStorage.getItem('proxyhub-logs-filters')
      expect(raw).toContain('"method":"all"')
      expect(raw).toContain('"search":""')
    })
  })
})
