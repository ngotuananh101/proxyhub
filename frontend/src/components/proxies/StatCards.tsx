import { useQuery } from '@tanstack/react-query'
import {
  CircleCheckIcon,
  CircleHelpIcon,
  CircleXIcon,
  GlobeIcon,
} from 'lucide-react'
import { fetchStats } from '@/api/proxies'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

const cards = [
  { key: 'total', label: 'Total proxies', icon: GlobeIcon },
  { key: 'alive', label: 'Alive', icon: CircleCheckIcon },
  { key: 'dead', label: 'Dead', icon: CircleXIcon },
  { key: 'unknown', label: 'Unknown', icon: CircleHelpIcon },
] as const

export function StatCards() {
  const { data, isPending } = useQuery({ queryKey: ['stats'], queryFn: fetchStats })

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.key} size="sm">
          <CardContent className="flex items-center gap-2.5">
            <card.icon className="size-4 shrink-0 text-muted-foreground" />
            <span className="truncate text-sm text-muted-foreground">
              {card.label}
            </span>
            <span className="ml-auto text-lg font-semibold tabular-nums">
              {isPending || !data ? (
                <Skeleton className="h-6 w-10" />
              ) : (
                data[card.key]
              )}
            </span>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
