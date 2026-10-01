import React, { useEffect, useMemo, useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listTenants, type TenantItem } from '@/api/tenants'
import { getMe } from '@/api/auth'
import { isAuthenticated } from '@/lib/auth'
import { TenantContext } from './tenant-context'

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

  const [selectedTenant, setSelectedTenant] = useState<TenantItem | null>(null)

  // Resolve the active tenant during render instead of storing it in an
  // effect: prefer an explicit selection, then the stored id, then 'default',
  // then the first tenant. Keeps the value consistent with the loaded list
  // without an extra render pass.
  const activeTenant = useMemo(() => {
    if (!tenants || tenants.length === 0) return null
    if (selectedTenant && tenants.some((t) => t.id === selectedTenant.id)) {
      return selectedTenant
    }
    const storedIdStr = localStorage.getItem(STORAGE_KEY)
    const storedId = storedIdStr ? parseInt(storedIdStr, 10) : null
    if (storedId) {
      const match = tenants.find((t) => t.id === storedId)
      if (match) return match
    }
    return tenants.find((t) => t.slug === 'default') ?? tenants[0]
  }, [tenants, selectedTenant])

  // Persist the resolved tenant so the choice survives a reload.
  useEffect(() => {
    if (activeTenant) {
      localStorage.setItem(STORAGE_KEY, String(activeTenant.id))
    }
  }, [activeTenant])

  const setActiveTenant = useCallback(
    (tenant: TenantItem) => {
      setSelectedTenant(tenant)
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
