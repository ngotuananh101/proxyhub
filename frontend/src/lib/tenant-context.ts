import { createContext, useContext } from 'react'
import type { TenantItem } from '@/api/tenants'

export interface TenantContextValue {
  activeTenant: TenantItem | null
  availableTenants: TenantItem[]
  setActiveTenant: (tenant: TenantItem) => void
  isLoading: boolean
  refreshTenants: () => Promise<void>
}

export const TenantContext = createContext<TenantContextValue | undefined>(undefined)

export function useTenant(): TenantContextValue {
  const context = useContext(TenantContext)
  if (!context) {
    throw new Error('useTenant must be used within a TenantProvider')
  }
  return context
}
