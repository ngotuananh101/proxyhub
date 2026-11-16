import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  PlusIcon,
  RefreshCwIcon,
  RotateCcwIcon,
  SearchIcon,
  Trash2Icon,
  UploadIcon,
} from 'lucide-react'
import {
  clearDeadProxies,
  deleteManyProxies,
  deleteProxy,
  fetchProxies,
  triggerCheckAll,
  type ProxyItem,
} from '@/api/proxies'
import { AddProxyDialog } from '@/components/proxies/AddProxyDialog'
import { EditProxyDialog } from '@/components/proxies/EditProxyDialog'
import { ImportDialog } from '@/components/proxies/ImportDialog'
import { ProxyTable } from '@/components/proxies/ProxyTable'
import { StatCards } from '@/components/proxies/StatCards'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from '@/components/ui/toast'
import { useRealtime } from '@/hooks/useRealtime'
import { useLocalStorage } from '@/hooks/use-local-storage'
import { useTenant } from '@/lib/tenant-context'

const PROXIES_FILTERS_KEY = 'proxyhub-proxies-filters'

const statusItems = [
  { label: 'All', value: 'all' },
  { label: 'Alive', value: 'alive' },
  { label: 'Dead', value: 'dead' },
  { label: 'Unknown', value: 'unknown' },
]

const pageSizeItems = [
  { label: '10', value: '10' },
  { label: '20', value: '20' },
  { label: '50', value: '50' },
  { label: '100', value: '100' },
]

export default function ProxiesPage() {
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useLocalStorage(PROXIES_FILTERS_KEY, {
    pageSize: 20,
    statusFilter: 'all',
    search: '',
  })
  const { pageSize, statusFilter, search } = filters
  const setPageSize = (pageSize: number) => setFilters((prev) => ({ ...prev, pageSize }))
  const setStatusFilter = (statusFilter: string) => setFilters((prev) => ({ ...prev, statusFilter }))
  const setSearch = (search: string) => setFilters((prev) => ({ ...prev, search }))
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [showImport, setShowImport] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [editingProxy, setEditingProxy] = useState<ProxyItem | null>(null)
  const [checking, setChecking] = useState(false)
  const [clearing, setClearing] = useState(false)
  const queryClient = useQueryClient()
  const { activeTenantId: tenantId, isResolvingTenant } = useTenant()

  // A selection only ever refers to rows visible under the current page and
  // filters. Rather than resetting it from an effect, remember which view it
  // belongs to and clear it during render when the view changes — the same
  // "adjust state while rendering" pattern React documents for derived resets.
  const viewKey = `${tenantId}|${page}|${pageSize}|${statusFilter}|${search}`
  const [selectionViewKey, setSelectionViewKey] = useState(viewKey)
  if (selectionViewKey !== viewKey) {
    setSelectionViewKey(viewKey)
    setSelected(new Set())
  }

  // Refresh stats and the table live as health check results stream in.
  // The server sends one `stats` event per tenant, and a member only receives
  // their own tenants' events; the check below is a second line of defence (and
  // covers an admin viewing one tenant while another tenant's pool changes).
  useRealtime((event) => {
    if (event.topic !== 'stats') return
    const eventTenantId = event.data.tenant_id
    if (tenantId != null && eventTenantId != null && eventTenantId !== tenantId) return
    queryClient.invalidateQueries({ queryKey: ['stats'] })
    queryClient.invalidateQueries({ queryKey: ['proxies'] })
  })

  const handleCheckAll = async () => {
    setChecking(true)
    try {
      await triggerCheckAll()
      toast.add({
        type: 'success',
        title: 'Health check requested',
        description: 'Results will update in a few minutes.',
      })
    } catch {
      toast.add({
        type: 'error',
        title: 'Failed to request health check',
      })
    } finally {
      setChecking(false)
    }
  }

  const { data, isPending } = useQuery({
    // The tenant id belongs in the key: it separates each tenant's cached
    // pages so a switcher change never shows another tenant's rows. Calls to
    // invalidateQueries keep the short `['proxies']` prefix, which still
    // matches every tenant.
    queryKey: ['proxies', tenantId, page, pageSize, statusFilter, search],
    queryFn: () =>
      fetchProxies({
        page,
        size: pageSize,
        status: statusFilter === 'all' ? undefined : statusFilter,
        q: search || undefined,
      }),
    enabled: !isResolvingTenant,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['proxies'] })
    queryClient.invalidateQueries({ queryKey: ['stats'] })
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteProxy(id)
    } catch {
      toast.add({ type: 'error', title: 'Failed to delete proxy' })
      return
    }
    setSelected((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
    toast.add({ type: 'success', title: 'Proxy deleted' })
    invalidate()
  }

  const handleDeleteSelected = async () => {
    try {
      await deleteManyProxies([...selected])
    } catch {
      // Keep the selection: the user's next attempt should not require
      // re-picking everything they had chosen.
      toast.add({ type: 'error', title: 'Failed to delete selected proxies' })
      return
    }
    toast.add({ type: 'success', title: `Deleted ${selected.size} proxies` })
    setSelected(new Set())
    invalidate()
  }

  const handleClearDead = async () => {
    setClearing(true)
    try {
      const { deleted } = await clearDeadProxies()
      toast.add({
        type: 'success',
        title: deleted > 0 ? `Removed ${deleted} dead proxies` : 'No dead proxies to remove',
      })
      setSelected(new Set())
      invalidate()
    } catch {
      toast.add({ type: 'error', title: 'Failed to clear dead proxies' })
    } finally {
      setClearing(false)
    }
  }

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  // Selection state tracks ids, so "all selected" must be derived from the ids
  // actually on show — comparing sizes would call a same-count selection on a
  // different page "all selected".
  const currentIds = data?.items.map((p) => p.id) ?? []
  const allSelected = currentIds.length > 0 && currentIds.every((id) => selected.has(id))
  const someSelected = !allSelected && currentIds.some((id) => selected.has(id))

  const toggleSelectAll = () => {
    if (!data) return
    setSelected(allSelected ? new Set() : new Set(currentIds))
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <h1 className="text-xl font-semibold tracking-tight">Proxies</h1>
          <p className="text-xs text-muted-foreground">
            Manage your proxy pool
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleCheckAll} disabled={checking}>
            <RefreshCwIcon data-icon="inline-start" />
            Check now
          </Button>
          <Button onClick={() => setShowForm(true)}>
            <PlusIcon data-icon="inline-start" />
            Add Proxy
          </Button>
          <Button variant="outline" onClick={() => setShowImport(true)}>
            <UploadIcon data-icon="inline-start" />
            Import
          </Button>
          <Button variant="outline" onClick={handleClearDead} disabled={clearing}>
            <Trash2Icon data-icon="inline-start" />
            Clear dead
          </Button>
          {selected.size > 0 && (
            <Button variant="destructive" onClick={handleDeleteSelected}>
              Delete ({selected.size})
            </Button>
          )}
        </div>
      </div>

      <StatCards />

      <div className="flex flex-wrap gap-3">
        <div className="relative w-64">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search host..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
            className="pl-8"
          />
        </div>
        <Select
          items={statusItems}
          value={statusFilter}
          onValueChange={(value) => {
            setStatusFilter(value ?? 'all')
            setPage(1)
          }}
        >
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {statusItems.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          aria-label="Clear filters"
          disabled={search === '' && statusFilter === 'all'}
          onClick={() => {
            setFilters((prev) => ({ ...prev, search: '', statusFilter: 'all' }))
            setPage(1)
          }}
        >
          <RotateCcwIcon data-icon="inline-start" />
          Clear filters
        </Button>
      </div>

      {isPending || !data ? (
        <Skeleton className="min-h-0 w-full flex-1" />
      ) : data.items.length === 0 ? (
        <Empty>
          <EmptyMedia variant="icon">
            <SearchIcon />
          </EmptyMedia>
          <EmptyTitle>No proxies found</EmptyTitle>
          <EmptyDescription>
            Add a proxy manually or import a batch to get started.
          </EmptyDescription>
        </Empty>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-4">
          <ProxyTable
            proxies={data.items}
            selected={selected}
            allSelected={allSelected}
            someSelected={someSelected}
            onToggleSelect={toggleSelect}
            onToggleSelectAll={toggleSelectAll}
            onEdit={setEditingProxy}
            onDelete={handleDelete}
          />
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
            <span>
              Page {data.page}/{Math.max(1, Math.ceil(data.total / data.size))} —{' '}
              {data.total} records total
            </span>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <span>Rows per page</span>
                <Select
                  items={pageSizeItems}
                  value={String(pageSize)}
                  onValueChange={(value) => {
                    setPageSize(Number(value ?? '20'))
                    setPage(1)
                  }}
                >
                  <SelectTrigger className="w-20">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {pageSizeItems.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  <ChevronLeftIcon data-icon="inline-start" />
                  Prev
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page * data.size >= data.total}
                  onClick={() => setPage(page + 1)}
                >
                  Next
                  <ChevronRightIcon data-icon="inline-end" />
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      <ImportDialog
        open={showImport}
        onOpenChange={setShowImport}
        onImported={invalidate}
      />
      <AddProxyDialog
        open={showForm}
        onOpenChange={setShowForm}
        onCreated={invalidate}
      />
      <EditProxyDialog
        proxy={editingProxy}
        onOpenChange={() => setEditingProxy(null)}
        onUpdated={invalidate}
      />
    </div>
  )
}
