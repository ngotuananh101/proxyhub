import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  PlusIcon,
  RefreshCwIcon,
  SearchIcon,
  UploadIcon,
} from 'lucide-react'
import {
  deleteManyProxies,
  deleteProxy,
  fetchProxies,
  triggerCheckAll,
} from '@/api/proxies'
import { AddProxyDialog } from '@/components/proxies/AddProxyDialog'
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

const statusItems = [
  { label: 'All', value: 'all' },
  { label: 'Alive', value: 'alive' },
  { label: 'Dead', value: 'dead' },
  { label: 'Unknown', value: 'unknown' },
]

export default function ProxiesPage() {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [showImport, setShowImport] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [checking, setChecking] = useState(false)
  const queryClient = useQueryClient()

  const handleCheckAll = async () => {
    setChecking(true)
    try {
      await triggerCheckAll()
      toast.add({
        type: 'success',
        title: 'Đã gửi yêu cầu kiểm tra sức khoẻ',
        description: 'Kết quả sẽ cập nhật sau vài phút.',
      })
    } catch {
      toast.add({
        type: 'error',
        title: 'Không thể gửi yêu cầu kiểm tra',
      })
    } finally {
      setChecking(false)
    }
  }

  const { data, isPending } = useQuery({
    queryKey: ['proxies', page, statusFilter, search],
    queryFn: () =>
      fetchProxies({
        page,
        status: statusFilter === 'all' ? undefined : statusFilter,
        q: search || undefined,
      }),
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['proxies'] })
    queryClient.invalidateQueries({ queryKey: ['stats'] })
  }

  const handleDelete = async (id: number) => {
    await deleteProxy(id)
    setSelected((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
    toast.add({ type: 'success', title: 'Đã xoá proxy' })
    invalidate()
  }

  const handleDeleteSelected = async () => {
    await deleteManyProxies([...selected])
    toast.add({ type: 'success', title: `Đã xoá ${selected.size} proxy` })
    setSelected(new Set())
    invalidate()
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

  const toggleSelectAll = () => {
    if (!data) return
    if (selected.size === data.items.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(data.items.map((p) => p.id)))
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">Proxies</h1>
          <p className="text-sm text-muted-foreground">
            Quản lý pool proxy của bạn
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleCheckAll} disabled={checking}>
            <RefreshCwIcon data-icon="inline-start" />
            Kiểm tra ngay
          </Button>
          <Button onClick={() => setShowForm(true)}>
            <PlusIcon data-icon="inline-start" />
            Add Proxy
          </Button>
          <Button variant="outline" onClick={() => setShowImport(true)}>
            <UploadIcon data-icon="inline-start" />
            Import
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
      </div>

      {isPending || !data ? (
        <Skeleton className="min-h-0 w-full flex-1" />
      ) : data.items.length === 0 ? (
        <Empty>
          <EmptyMedia variant="icon">
            <SearchIcon />
          </EmptyMedia>
          <EmptyTitle>Không có proxy nào</EmptyTitle>
          <EmptyDescription>
            Thêm proxy thủ công hoặc import hàng loạt để bắt đầu.
          </EmptyDescription>
        </Empty>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-6">
          <ProxyTable
            proxies={data.items}
            selected={selected}
            onToggleSelect={toggleSelect}
            onToggleSelectAll={toggleSelectAll}
            onDelete={handleDelete}
          />
          <div className="flex shrink-0 items-center justify-between text-sm text-muted-foreground">
            <span>
              Page {data.page} — {data.total} total
            </span>
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
    </div>
  )
}
