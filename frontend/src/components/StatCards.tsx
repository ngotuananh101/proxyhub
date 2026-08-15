import { useQuery } from '@tanstack/react-query'
import { fetchStats } from '../api/proxies'

const cards = [
  { key: 'total', label: 'Total', color: 'text-white' },
  { key: 'alive', label: 'Alive', color: 'text-green-400' },
  { key: 'dead', label: 'Dead', color: 'text-red-400' },
  { key: 'unknown', label: 'Unknown', color: 'text-yellow-400' },
] as const

export default function StatCards() {
  const { data } = useQuery({ queryKey: ['stats'], queryFn: fetchStats })

  return (
    <div className="grid grid-cols-4 gap-4">
      {cards.map((c) => (
        <div key={c.key} className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
          <p className="text-sm text-zinc-400">{c.label}</p>
          <p className={`text-2xl font-bold ${c.color}`}>{data?.[c.key] ?? '—'}</p>
        </div>
      ))}
    </div>
  )
}
