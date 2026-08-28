import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TenantProvider } from '../lib/tenant'
import TenantsPage from '../pages/TenantsPage'
import * as tenantsApi from '../api/tenants'
import * as authApi from '../api/auth'
import * as settingsApi from '../api/settings'

const mockTenants = [
  { id: 1, name: 'Default', slug: 'default', created_at: '2026-01-01T00:00:00' },
  { id: 2, name: 'Beta Team', slug: 'beta', created_at: '2026-01-02T00:00:00' },
]

describe('TenantsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    localStorage.setItem('access_token', 'fake-token')
  })

  it('renders tenant table and create button', async () => {
    vi.spyOn(authApi, 'getMe').mockResolvedValue({ id: 1, username: 'admin', is_admin: true, email: null })
    vi.spyOn(tenantsApi, 'listTenants').mockResolvedValue(mockTenants)
    vi.spyOn(settingsApi, 'fetchSettings').mockResolvedValue({
      items: [{ key: 'TIMEZONE', label: 'Timezone', description: '', type: 'string', default: 'UTC', min: null, max: null, value: 'UTC' }],
    })

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <TenantProvider>
            <TenantsPage />
          </TenantProvider>
        </BrowserRouter>
      </QueryClientProvider>
    )

    expect(await screen.findByText('Default')).toBeInTheDocument()
    expect(screen.getByText('Beta Team')).toBeInTheDocument()
    expect(screen.getByText('Create Tenant')).toBeInTheDocument()
  })

  it('shows loading skeletons while tenants are being fetched', async () => {
    vi.spyOn(authApi, 'getMe').mockResolvedValue({ id: 1, username: 'admin', is_admin: true, email: null })
    vi.spyOn(tenantsApi, 'listTenants').mockImplementation(() => new Promise(() => {}))
    vi.spyOn(settingsApi, 'fetchSettings').mockResolvedValue({
      items: [{ key: 'TIMEZONE', label: 'Timezone', description: '', type: 'string', default: 'UTC', min: null, max: null, value: 'UTC' }],
    })

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <TenantProvider>
            <TenantsPage />
          </TenantProvider>
        </BrowserRouter>
      </QueryClientProvider>
    )

    expect(screen.getByText('Tenants')).toBeInTheDocument()
    // Loading state renders skeleton rows (3 placeholder rows)
    const skeletonDivs = document.querySelectorAll('.animate-pulse.bg-muted')
    expect(skeletonDivs.length).toBeGreaterThan(0)
  })

  it('shows empty state when no tenants exist', async () => {
    vi.spyOn(authApi, 'getMe').mockResolvedValue({ id: 1, username: 'admin', is_admin: true, email: null })
    vi.spyOn(tenantsApi, 'listTenants').mockResolvedValue([])
    vi.spyOn(settingsApi, 'fetchSettings').mockResolvedValue({
      items: [{ key: 'TIMEZONE', label: 'Timezone', description: '', type: 'string', default: 'UTC', min: null, max: null, value: 'UTC' }],
    })

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <TenantProvider>
            <TenantsPage />
          </TenantProvider>
        </BrowserRouter>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('No tenants found.')).toBeInTheDocument()
    })
  })
})
