import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { PencilIcon, PlusIcon, RefreshCwIcon, Trash2Icon } from 'lucide-react'
import {
  deleteSource,
  fetchSourceNow,
  fetchSources,
  updateSource,
  type SourceItem,
} from '@/api/sources'
import { SourceDialog } from '@/components/sources/SourceDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Empty, EmptyDescription, EmptyTitle } from '@/components/ui/empty'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { toast } from '@/components/ui/toast'

function StatusBadge({ source }: { source: SourceItem }) {
  if (!source.last_status) {
    return <Badge variant="secondary">never fetched</Badge>
  }
  const ok = source.last_status.startsWith('ok')
  return (
    <Badge variant={ok ? 'default' : 'destructive'} className={ok ? 'text-success' : undefined}>
      {ok ? 'ok' : 'error'}
    </Badge>
  )
}

export default function SourcesPage() {
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<SourceItem | null>(null)
  const [fetchingId, setFetchingId] = useState<number | null>(null)

  const { data, isPending } = useQuery({ queryKey: ['sources'], queryFn: fetchSources })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['sources'] })
    queryClient.invalidateQueries({ queryKey: ['proxies'] })
    queryClient.invalidateQueries({ queryKey: ['stats'] })
  }

  const handleToggle = async (source: SourceItem) => {
    try {
      await updateSource(source.id, { enabled: !source.enabled })
      queryClient.invalidateQueries({ queryKey: ['sources'] })
    } catch {
      toast.add({ type: 'error', title: 'Failed to update source' })
    }
  }

  const handleFetchNow = async (source: SourceItem) => {
    setFetchingId(source.id)
    try {
      const res = await fetchSourceNow(source.id)
      const ok = res.status.startsWith('ok')
      toast.add({
        type: ok ? 'success' : 'error',
        title: ok ? 'Fetch completed' : 'Fetch failed',
        description: res.status,
      })
      refresh()
    } catch {
      toast.add({ type: 'error', title: 'Failed to fetch source' })
    } finally {
      setFetchingId(null)
    }
  }

  const handleDelete = async (source: SourceItem) => {
    try {
      await deleteSource(source.id)
      toast.add({ type: 'success', title: 'Source deleted' })
      queryClient.invalidateQueries({ queryKey: ['sources'] })
    } catch {
      toast.add({ type: 'error', title: 'Failed to delete source' })
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Sources</h1>
          <p className="text-xs text-muted-foreground">
            Free proxy list feeds. Fetched proxies are imported as unknown and
            classified by the next health check.
          </p>
        </div>
        <Button
          onClick={() => {
            setEditing(null)
            setDialogOpen(true)
          }}
        >
          <PlusIcon data-icon="inline-start" />
          Add Source
        </Button>
      </div>

      {isPending ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : data && data.length > 0 ? (
        <ScrollArea className="sticky-table-header min-h-0 flex-1 bg-card">
          <Table>
            <TableHeader className="[&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:bg-card">
              <TableRow>
                <TableHead className="w-12">On</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>URL</TableHead>
                <TableHead>Interval</TableHead>
                <TableHead>Last fetch</TableHead>
                <TableHead>Last status</TableHead>
                <TableHead className="w-32 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((source) => (
                <TableRow key={source.id}>
                  <TableCell>
                    <Checkbox
                      checked={source.enabled}
                      onCheckedChange={() => handleToggle(source)}
                      aria-label={`Enable ${source.name}`}
                    />
                  </TableCell>
                  <TableCell className="font-medium">{source.name}</TableCell>
                  <TableCell className="max-w-64">
                    <span className="block truncate text-xs text-muted-foreground">
                      {source.url}
                    </span>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-sm">
                    {source.interval_minutes} min
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-sm">
                    {source.last_fetched_at
                      ? new Date(source.last_fetched_at).toLocaleString()
                      : '—'}
                  </TableCell>
                  <TableCell className="max-w-56">
                    <div className="flex items-center gap-2">
                      <StatusBadge source={source} />
                      {source.last_status && (
                        <span className="truncate text-xs text-muted-foreground">
                          {source.last_status}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleFetchNow(source)}
                        disabled={fetchingId === source.id}
                        aria-label={`Fetch ${source.name} now`}
                      >
                        <RefreshCwIcon
                          className={fetchingId === source.id ? 'animate-spin' : undefined}
                        />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setEditing(source)
                          setDialogOpen(true)
                        }}
                        aria-label={`Edit ${source.name}`}
                      >
                        <PencilIcon />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(source)}
                        aria-label={`Delete ${source.name}`}
                      >
                        <Trash2Icon />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollArea>
      ) : (
        <Empty>
          <EmptyTitle>No sources yet</EmptyTitle>
          <EmptyDescription>
            Add a free proxy list URL to start importing proxies automatically.
          </EmptyDescription>
        </Empty>
      )}

      <SourceDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onSaved={() => queryClient.invalidateQueries({ queryKey: ['sources'] })}
        source={editing}
      />
    </div>
  )
}
