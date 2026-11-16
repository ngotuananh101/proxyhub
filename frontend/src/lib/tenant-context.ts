import { createContext, useContext } from 'react'
import type { TenantItem } from '@/api/tenants'

export interface TenantContextValue {
  activeTenant: TenantItem | null
  /**
   * Id to scope cache keys and requests by. It is resolved synchronously from
   * the stored selection, so it does not flip from `null` to a number once the
   * tenant list arrives — that would refetch every tenant-scoped query.
   * `null` for a non-admin, who never loads the tenant list.
   */
  activeTenantId: number | null
  /**
   * True while the id above is still being determined. Tenant-scoped queries
   * stay disabled until then, so the first visit does not fetch once under a
   * `null` key and again under the resolved id.
   */
  isResolvingTenant: boolean
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
