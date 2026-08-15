import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ProxyTable } from '../components/proxies/ProxyTable'
import type { ProxyItem } from '../api/proxies'

const mockProxies: ProxyItem[] = [
  {
    id: 1, scheme: 'http', host: '1.2.3.4', port: 8080,
    username: null, password: null, status: 'alive',
    latency_ms: 120, last_checked_at: null,
    created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00',
  },
  {
    id: 2, scheme: 'http', host: '5.6.7.8', port: 3128,
    username: 'user', password: 'pass', status: 'dead',
    latency_ms: null, last_checked_at: null,
    created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00',
  },
]

describe('ProxyTable', () => {
  it('renders proxy rows', () => {
    render(
      <ProxyTable
        proxies={mockProxies}
        selected={new Set()}
        onToggleSelect={() => {}}
        onToggleSelectAll={() => {}}
        onDelete={() => {}}
      />
    )
    expect(screen.getByText('1.2.3.4:8080')).toBeInTheDocument()
    expect(screen.getByText('5.6.7.8:3128')).toBeInTheDocument()
    expect(screen.getByText('alive')).toBeInTheDocument()
    expect(screen.getByText('dead')).toBeInTheDocument()
  })
})
