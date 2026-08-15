import { useQuery } from '@tanstack/react-query'
import {
  CircleCheckIcon,
  CircleHelpIcon,
  CircleXIcon,
  GlobeIcon,
} from 'lucide-react'
import { fetchStats } from '@/api/proxies'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

const cards = [
  { key: 'total', label: 'Tổng proxy', icon: GlobeIcon },
  { key: 'alive', label: 'Alive', icon: CircleCheckIcon },
  { key: 'dead', label: 'Dead', icon: CircleXIcon },
  { key: 'unknown', label: 'Unknown', icon: CircleHelpIcon },
] as const

export function StatCards() {
  const { data, isPending } = useQuery({ queryKey: ['stats'], queryFn: fetchStats })

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.key}>
          <CardHeader className="flex-row items-center justify-between">
            <CardDescription>{card.label}</CardDescription>
            <card.icon className="text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isPending || !data ? (
              <Skeleton className="h-7 w-12" />
            ) : (
              <p className="text-2xl font-semibold tabular-nums">{data[card.key]}</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
