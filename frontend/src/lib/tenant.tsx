import React, { useEffect, useMemo, useState, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listTenants, type TenantItem } from '@/api/tenants'
import { getMe } from '@/api/auth'
import { isAuthenticated } from '@/lib/auth'
import { TenantContext } from './tenant-context'

const STORAGE_KEY = 'selected_tenant_id'

function readStoredTenantId(): number | null {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  const id = parseInt(raw, 10)
  return Number.isFinite(id) ? id : null
}

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const authenticated = isAuthenticated()

  const { data: user, isPending: isUserPending } = useQuery({
    queryKey: ['me'],
    queryFn: getMe,
    enabled: authenticated,
  })

  const {
    data: tenants = [],
    isLoading,
    isPending: isTenantsPending,
    refetch,
  } = useQuery({
    queryKey: ['tenants'],
    queryFn: listTenants,
    enabled: authenticated && user?.is_admin === true,
  })

  // Seeded from storage rather than from `null`: the persisted choice is
  // already trustworthy, and waiting for the tenant list to confirm it would
  // flip every tenant-scoped query key from `null` to the id and fetch twice.
  const [selectedTenantId, setSelectedTenantId] = useState<number | null>(readStoredTenantId)

  // Resolve the active tenant during render instead of storing it in an
  // effect: prefer an explicit selection, then the stored id, then 'default',
  // then the first tenant. Keeps the value consistent with the loaded list
  // without an extra render pass.
  const activeTenant = useMemo(() => {
    if (!tenants || tenants.length === 0) return null
    if (selectedTenantId != null) {
      const match = tenants.find((t) => t.id === selectedTenantId)
      if (match) return match
    }
    return tenants.find((t) => t.slug === 'default') ?? tenants[0]
  }, [tenants, selectedTenantId])

  // The stored id is used until the list resolves. That is safe: the API
  // ignores the header for a tenant the user cannot reach, and a non-admin has
  // no selection at all (the list endpoint is admin-only).
  const activeTenantId = activeTenant?.id ?? selectedTenantId

  // Until `me` answers we do not know whether the tenant list will ever load.
  // A stored id is enough to start; without one, wait for the list — but only
  // if the list is actually going to load. For a non-admin it never does, so
  // its query stays `pending` forever and would block their pages for good.
  const tenantsWillLoad = authenticated && user?.is_admin === true
  const isResolvingTenant =
    authenticated &&
    activeTenantId == null &&
    (isUserPending || (tenantsWillLoad && isTenantsPending))

  // Persist the resolved tenant so the choice survives a reload.
  useEffect(() => {
    if (activeTenant) {
      localStorage.setItem(STORAGE_KEY, String(activeTenant.id))
    }
  }, [activeTenant])

  const setActiveTenant = useCallback(
    (tenant: TenantItem) => {
      setSelectedTenantId(tenant.id)
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
        activeTenantId,
        isResolvingTenant,
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
