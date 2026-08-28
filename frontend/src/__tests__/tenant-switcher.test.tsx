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
