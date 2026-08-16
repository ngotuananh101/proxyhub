import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchLogs, type LogItem } from '@/api/logs'
import { Badge } from '@/components/ui/badge'
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
import { useRealtime } from '@/hooks/useRealtime'

const MAX_ROWS = 200

function formatBytes(n: number | null): string {
  if (n === null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export default function LogsPage() {
  const { data, isPending } = useQuery({
    queryKey: ['logs'],
    queryFn: () => fetchLogs(MAX_ROWS),
  })
  const [rows, setRows] = useState<LogItem[]>([])

  useEffect(() => {
    if (data) setRows(data)
  }, [data])

  useRealtime((event) => {
    if (event.topic !== 'logs') return
    const log = event.data as unknown as LogItem
    setRows((prev) => [log, ...prev.filter((r) => r.id !== log.id)].slice(0, MAX_ROWS))
  })

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-4">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Request Logs</h1>
          <p className="text-xs text-muted-foreground">
            Requests forwarded through the gateway, updated in real time.
          </p>
        </div>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="size-2 animate-pulse rounded-full bg-success" />
          Live
        </span>
      </div>

      {isPending ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <Empty>
          <EmptyTitle>No requests yet</EmptyTitle>
          <EmptyDescription>
            Route traffic through the gateway to see live request logs.
          </EmptyDescription>
        </Empty>
      ) : (
        <ScrollArea className="sticky-table-header min-h-0 min-w-0 flex-1 bg-card">
          <Table>
            <TableHeader className="[&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:bg-card">
              <TableRow>
                <TableHead className="w-28">Time</TableHead>
                <TableHead className="w-32">Client</TableHead>
                <TableHead className="w-20">Method</TableHead>
                <TableHead>Target</TableHead>
                <TableHead className="w-44">Proxy</TableHead>
                <TableHead className="w-24 text-right">Size</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((log) => (
                <TableRow key={log.id}>
                  <TableCell className="whitespace-nowrap text-xs tabular-nums text-muted-foreground">
                    {new Date(log.created_at).toLocaleTimeString()}
                  </TableCell>
                  <TableCell className="text-xs">{log.client_ip ?? '—'}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{log.method ?? '—'}</Badge>
                  </TableCell>
                  <TableCell className="max-w-96">
                    <span className="block truncate text-sm">
                      {log.host ?? '—'}
                      {log.path && (
                        <span className="text-muted-foreground">{log.path}</span>
                      )}
                    </span>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {log.proxy_host ? `${log.proxy_host}:${log.proxy_port}` : '—'}
                  </TableCell>
                  <TableCell className="text-right text-xs tabular-nums">
                    {formatBytes(log.response_bytes)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollArea>
      )}
    </div>
  )
}
