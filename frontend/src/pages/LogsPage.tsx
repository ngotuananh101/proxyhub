import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { CalendarIcon, ChevronLeftIcon, ChevronRightIcon, SearchIcon } from 'lucide-react'
import { type DateRange } from 'react-day-picker'
import { fetchLogs, type LogItem } from '@/api/logs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Empty, EmptyDescription, EmptyTitle } from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
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
import { useTenant } from '@/lib/tenant'
import { useTimezone } from '@/hooks/use-timezone'
import { formatDateTime } from '@/lib/datetime'


const methodItems = [
  { label: 'All', value: 'all' },
  { label: 'GET', value: 'GET' },
  { label: 'POST', value: 'POST' },
  { label: 'PUT', value: 'PUT' },
  { label: 'DELETE', value: 'DELETE' },
  { label: 'HEAD', value: 'HEAD' },
  { label: 'CONNECT', value: 'CONNECT' },
]

const pageSizeItems = [
  { label: '10', value: '10' },
  { label: '20', value: '20' },
  { label: '50', value: '50' },
  { label: '100', value: '100' },
]

function formatBytes(n: number | null): string {
  if (n === null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export default function LogsPage() {
  const timezone = useTimezone()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [method, setMethod] = useState('all')
  const [search, setSearch] = useState('')
  const [date, setDate] = useState<DateRange | undefined>(undefined)

  // Convert the selected day range into UTC ISO instants accepted by the API.
  // A day boundary is inclusive at the start and exclusive at the end, so the
  // range covers the full end day.
  const range = useMemo(() => {
    if (!date?.from) return { start: '', end: '' }
    const from = new Date(date.from)
    from.setHours(0, 0, 0, 0)
    const to = date.to ? new Date(date.to) : new Date(date.from)
    to.setDate(to.getDate() + 1)
    to.setHours(0, 0, 0, 0)
    return {
      start: from.toISOString(),
      end: to.toISOString(),
    }
  }, [date])
  const { start, end } = range

  // Live logs are only prepended in-place on the latest, unfiltered view.
  // Filtered or older pages simply refetch when new logs arrive.
  const liveRef = useRef(true)
  liveRef.current = page === 1 && method === 'all' && !search && !start && !end

  const { data, isPending } = useQuery({
    queryKey: ['logs', { page, pageSize, method, search, start, end }],
    queryFn: () =>
      fetchLogs({
        page,
        size: pageSize,
        method: method === 'all' ? undefined : method,
        q: search || undefined,
        start: start || undefined,
        end: end || undefined,
      }),
  })
  const [rows, setRows] = useState<LogItem[]>([])

  useEffect(() => {
    if (data) setRows(data.items)
  }, [data])

  // Buffer log events arriving in the same tick and prepend them in one flush,
  // so a burst of requests causes one render instead of one per event.
  const bufferRef = useRef<LogItem[]>([])
  const flushScheduledRef = useRef(false)

  const { activeTenant } = useTenant()
  const activeTenantIdRef = useRef<number | null>(null)
  activeTenantIdRef.current = activeTenant?.id ?? null

  useRealtime((event) => {
    if (event.topic !== 'logs') return
    if (!liveRef.current) {
      queryClient.invalidateQueries({ queryKey: ['logs'] })
      return
    }
    const log = event.data as unknown as LogItem
    // Only prepend log if it matches active tenant (or if tenant_id is not specified)
    if (log.tenant_id && activeTenantIdRef.current && log.tenant_id !== activeTenantIdRef.current) {
      return
    }
    bufferRef.current.push(log)
    if (flushScheduledRef.current) return
    flushScheduledRef.current = true
    setTimeout(() => {
      flushScheduledRef.current = false
      const incoming = bufferRef.current
      bufferRef.current = []
      if (incoming.length === 0) return
      setRows((prev) => {
        const ids = new Set(incoming.map((l) => l.id))
        return [...incoming, ...prev.filter((l) => !ids.has(l.id))].slice(0, 200)
      })
    })
  })

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1

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

      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <div className="relative w-64">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search host, path, proxy or IP..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
            className="pl-8"
          />
        </div>
        <Select
          items={methodItems}
          value={method}
          onValueChange={(value) => {
            setMethod(value ?? 'all')
            setPage(1)
          }}
        >
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {methodItems.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        <Popover>
          <PopoverTrigger
            render={
              <Button
                variant="outline"
                aria-label="Date range"
                className="w-64 justify-start px-2.5 font-normal"
              />
            }
          >
            <CalendarIcon data-icon="inline-start" />
            {date?.from ? (
              date.to ? (
                <>
                  {format(date.from, 'LLL dd, y')} - {format(date.to, 'LLL dd, y')}
                </>
              ) : (
                format(date.from, 'LLL dd, y')
              )
            ) : (
              <span className="text-muted-foreground">Pick a range</span>
            )}
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="range"
              defaultMonth={date?.from}
              selected={date}
              onSelect={(value) => {
                setDate(value ?? undefined)
                setPage(1)
              }}
              numberOfMonths={2}
            />
          </PopoverContent>
        </Popover>
        {date?.from && (
          <Button
            variant="ghost"
            className="text-xs font-bold uppercase tracking-wider"
            aria-label="Clear date filter"
            onClick={() => {
              setDate(undefined)
              setPage(1)
            }}
          >
            Clear
          </Button>
        )}
      </div>

      {isPending || !data ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <Empty>
          <EmptyTitle>No requests found</EmptyTitle>
          <EmptyDescription>
            Route traffic through the gateway to see request logs.
          </EmptyDescription>
        </Empty>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-4">
          <ScrollArea className="sticky-table-header min-h-0 min-w-0 flex-1 bg-card">
            <Table>
              <TableHeader className="[&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:bg-card">
                <TableRow>
                  <TableHead className="w-48">Time</TableHead>
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
                      {formatDateTime(log.created_at, timezone)}
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

          <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
            <span>
              Page {data.page}/{totalPages} — {data.total} records total
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
    </div>
  )
}
