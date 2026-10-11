import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as settingsApi from '@/api/settings'
import SettingsPage from '@/pages/SettingsPage'

const mockItems: settingsApi.SettingItem[] = [
  {
    key: 'TIMEZONE',
    label: 'Timezone',
    description: '',
    type: 'string',
    default: 'UTC',
    min: null,
    max: null,
    value: 'Asia/Ho_Chi_Minh',
  },
  {
    key: 'SOURCE_FETCH_TIMEOUT',
    label: 'Source fetch timeout (seconds)',
    description: '',
    type: 'float',
    default: 30,
    min: 5,
    max: 120,
    value: 45,
  },
  {
    key: 'DEAD_PROXY_RETENTION_DAYS',
    label: 'Dead proxy retention (days)',
    description: '',
    type: 'float',
    default: 7,
    min: 0,
    max: 365,
    value: 14,
  },
  {
    key: 'HEALTH_CHECK_URL',
    label: 'Health check URL',
    description: '',
    type: 'string',
    default: 'https://api.ipify.org',
    min: null,
    max: null,
    value: 'https://example.com/ip',
  },
  {
    key: 'HEALTH_CHECK_TIMEOUT',
    label: 'Health check timeout (seconds)',
    description: '',
    type: 'float',
    default: 6,
    min: 1,
    max: 60,
    value: 9,
  },
  {
    key: 'HEALTH_CHECK_INTERVAL',
    label: 'Health check interval (seconds)',
    description: '',
    type: 'float',
    default: 300,
    min: 60,
    max: 86400,
    value: 600,
  },
  {
    key: 'HEALTH_CHECK_CONCURRENCY',
    label: 'Health check concurrency',
    description: '',
    type: 'int',
    default: 50,
    min: 1,
    max: 500,
    value: 25,
  },
  {
    key: 'REQUEST_LOG_RETENTION_DAYS',
    label: 'Request log retention (days)',
    description: '',
    type: 'int',
    default: 30,
    min: 0,
    max: 3650,
    value: 60,
  },
]

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SettingsPage />
      </BrowserRouter>
    </QueryClientProvider>
  )
}

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('loads stored values into the inputs on first render', async () => {
    vi.spyOn(settingsApi, 'fetchSettings').mockResolvedValue({ items: mockItems })

    renderPage()

    // Numeric fields must show the server value without any save/refetch.
    await waitFor(() => {
      expect(screen.getByLabelText('Source fetch timeout (seconds)')).toHaveValue(45)
    })
    expect(screen.getByLabelText('Dead proxy retention (days)')).toHaveValue(14)
    expect(screen.getByLabelText('Health check timeout (seconds)')).toHaveValue(9)
    expect(screen.getByLabelText('Health check interval (seconds)')).toHaveValue(600)
    expect(screen.getByLabelText('Health check concurrency')).toHaveValue(25)
    expect(screen.getByLabelText('Request log retention (days)')).toHaveValue(60)

    // Text field must show the stored value too.
    expect(screen.getByLabelText('Health check URL')).toHaveValue('https://example.com/ip')
  })
})
