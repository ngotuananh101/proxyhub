import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import * as credentialsApi from '@/api/credentials'
import GatewayCredentialsPage from '@/pages/GatewayCredentialsPage'
import { TenantProvider } from '@/lib/tenant'

const mockCredentials: credentialsApi.CredentialItem[] = [
  {
    id: 1,
    tenant_id: 1,
    name: 'Scraper Bot',
    auth_mode: 'basic',
    username: 'scraper1',
    cidrs: null,
    is_active: true,
    last_used_at: '2026-08-29T10:00:00Z',
    created_at: '2026-08-20T10:00:00Z',
  },
  {
    id: 2,
    tenant_id: 1,
    name: 'Office Network',
    auth_mode: 'ip_whitelist',
    username: null,
    cidrs: '192.168.1.0/24',
    is_active: false,
    last_used_at: null,
    created_at: '2026-08-21T10:00:00Z',
  },
]

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <TenantProvider>
        <BrowserRouter>{ui}</BrowserRouter>
      </TenantProvider>
    </QueryClientProvider>
  )
}

describe('GatewayCredentialsPage', () => {
  it('renders table with credentials', async () => {
    vi.spyOn(credentialsApi, 'fetchCredentials').mockResolvedValue({
      items: mockCredentials,
      total: 2,
    })

    renderWithProviders(<GatewayCredentialsPage />)

    await waitFor(() => {
      expect(screen.getByText('Scraper Bot')).toBeInTheDocument()
      expect(screen.getByText('Office Network')).toBeInTheDocument()
      expect(screen.getByText('scraper1')).toBeInTheDocument()
      expect(screen.getByText('192.168.1.0/24')).toBeInTheDocument()
    })
  })
})
