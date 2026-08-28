import React, { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listTenants, type TenantItem } from '@/api/tenants'
import { getMe } from '@/api/auth'
import { isAuthenticated } from '@/lib/auth'

interface TenantContextValue {
  activeTenant: TenantItem | null
  availableTenants: TenantItem[]
  setActiveTenant: (tenant: TenantItem) => void
  isLoading: boolean
  refreshTenants: () => Promise<void>
}

const TenantContext = createContext<TenantContextValue | undefined>(undefined)

const STORAGE_KEY = 'selected_tenant_id'

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const authenticated = isAuthenticated()

  const { data: user } = useQuery({
    queryKey: ['me'],
    queryFn: getMe,
    enabled: authenticated,
  })

  const { data: tenants = [], isLoading, refetch } = useQuery({
    queryKey: ['tenants'],
    queryFn: listTenants,
    enabled: authenticated && user?.is_admin === true,
  })

  const [activeTenant, setActiveTenantState] = useState<TenantItem | null>(null)

  // Initialize or reconcile active tenant
  useEffect(() => {
    if (!tenants || tenants.length === 0) return

    const storedIdStr = localStorage.getItem(STORAGE_KEY)
    const storedId = storedIdStr ? parseInt(storedIdStr, 10) : null

    if (storedId) {
      const match = tenants.find((t) => t.id === storedId)
      if (match) {
        setActiveTenantState(match)
        return
      }
    }

    // Default to first tenant
    const defaultTenant = tenants.find((t) => t.slug === 'default') ?? tenants[0]
    setActiveTenantState(defaultTenant)
    localStorage.setItem(STORAGE_KEY, String(defaultTenant.id))
  }, [tenants])

  const setActiveTenant = useCallback(
    (tenant: TenantItem) => {
      setActiveTenantState(tenant)
      localStorage.setItem(STORAGE_KEY, String(tenant.id))
      // Invalidate all query caches so lists/stats refresh under new tenant
      queryClient.invalidateQueries()
    },
    [queryClient]
  )

  const refreshTenants = useCallback(async () => {
    await refetch()
  }, [refetch])

  return (
    <TenantContext.Provider
      value={{
        activeTenant,
        availableTenants: tenants,
        setActiveTenant,
        isLoading,
        refreshTenants,
      }}
    >
      {children}
    </TenantContext.Provider>
  )
}

export function useTenant(): TenantContextValue {
  const context = useContext(TenantContext)
  if (!context) {
    throw new Error('useTenant must be used within a TenantProvider')
  }
  return context
}
