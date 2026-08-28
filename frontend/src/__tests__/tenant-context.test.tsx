import { render, screen, act, waitFor } from '@testing-library/react'
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
    vi.spyOn(authApi, 'getMe').mockResolvedValueOnce({ id: 1, username: 'admin', is_admin: true, email: null })
    vi.spyOn(tenantsApi, 'listTenants').mockResolvedValueOnce(mockTenants)
    localStorage.setItem('access_token', 'fake-token')

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <TenantProvider>
          <ConsumerComponent />
        </TenantProvider>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('active')).toHaveTextContent('Default')
    })
    expect(screen.getByTestId('count')).toHaveTextContent('2')
    expect(localStorage.getItem('selected_tenant_id')).toBe('1')
  })

  it('switches active tenant and updates localStorage', async () => {
    vi.spyOn(authApi, 'getMe').mockResolvedValueOnce({ id: 1, username: 'admin', is_admin: true, email: null })
    vi.spyOn(tenantsApi, 'listTenants').mockResolvedValueOnce(mockTenants)
    localStorage.setItem('access_token', 'fake-token')

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <TenantProvider>
          <ConsumerComponent />
        </TenantProvider>
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('count')).toHaveTextContent('2')
    })
    await screen.findByText('Switch to Acme')
    act(() => {
      screen.getByText('Switch to Acme').click()
    })

    expect(screen.getByTestId('active')).toHaveTextContent('Acme Corp')
    expect(localStorage.getItem('selected_tenant_id')).toBe('2')
  })
})
