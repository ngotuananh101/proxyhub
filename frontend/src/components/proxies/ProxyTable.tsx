import { Trash2Icon } from 'lucide-react'
import type { ProxyItem } from '@/api/proxies'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const statusVariant: Record<string, 'default' | 'secondary' | 'destructive'> = {
  alive: 'default',
  dead: 'destructive',
  unknown: 'secondary',
}

interface Props {
  proxies: ProxyItem[]
  selected: Set<number>
  onToggleSelect: (id: number) => void
  onToggleSelectAll: () => void
  onDelete: (id: number) => void
}

export function ProxyTable({
  proxies,
  selected,
  onToggleSelect,
  onToggleSelectAll,
  onDelete,
}: Props) {
  const allSelected = proxies.length > 0 && selected.size === proxies.length
  const someSelected = selected.size > 0 && !allSelected

  return (
    <ScrollArea className="min-h-0 flex-1 bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <Checkbox
                checked={allSelected}
                indeterminate={someSelected}
                onCheckedChange={onToggleSelectAll}
                aria-label="Select all proxies"
              />
            </TableHead>
            <TableHead>Proxy</TableHead>
            <TableHead>Scheme</TableHead>
            <TableHead>Auth</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Latency</TableHead>
            <TableHead className="w-12" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {proxies.map((proxy) => (
            <TableRow
              key={proxy.id}
              data-state={selected.has(proxy.id) ? 'selected' : undefined}
            >
              <TableCell>
                <Checkbox
                  checked={selected.has(proxy.id)}
                  onCheckedChange={() => onToggleSelect(proxy.id)}
                  aria-label={`Select ${proxy.host}:${proxy.port}`}
                />
              </TableCell>
              <TableCell className="font-mono text-sm">
                {proxy.host}:{proxy.port}
              </TableCell>
              <TableCell>
                <Badge variant="outline">{proxy.scheme}</Badge>
              </TableCell>
              <TableCell>
                {proxy.username ? (
                  <Badge variant="secondary">auth</Badge>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell>
                <Badge variant={statusVariant[proxy.status] ?? 'secondary'}>
                  {proxy.status}
                </Badge>
              </TableCell>
              <TableCell className="tabular-nums">
                {proxy.latency_ms != null ? `${proxy.latency_ms} ms` : '—'}
              </TableCell>
              <TableCell>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  onClick={() => onDelete(proxy.id)}
                  aria-label={`Delete ${proxy.host}:${proxy.port}`}
                >
                  <Trash2Icon />
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </ScrollArea>
  )
}
