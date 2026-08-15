import { useState } from 'react'
import type { ProxyItem } from '../api/proxies'

const statusColors: Record<string, string> = {
  alive: 'bg-green-900 text-green-300',
  dead: 'bg-red-900 text-red-300',
  unknown: 'bg-yellow-900 text-yellow-300',
}

interface Props {
  proxies: ProxyItem[]
  selected: Set<number>
  onToggleSelect: (id: number) => void
  onToggleSelectAll: () => void
  onDelete: (id: number) => void
}

export default function ProxyTable({ proxies, selected, onToggleSelect, onToggleSelectAll, onDelete }: Props) {
  const [showCreds, setShowCreds] = useState<Set<number>>(new Set())

  const toggleCreds = (id: number) => {
    setShowCreds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="w-full text-sm text-left">
        <thead className="bg-zinc-900 text-zinc-400">
          <tr>
            <th className="p-3">
              <input type="checkbox" onChange={onToggleSelectAll} checked={selected.size === proxies.length && proxies.length > 0} />
            </th>
            <th className="p-3">Scheme</th>
            <th className="p-3">Host:Port</th>
            <th className="p-3">Credentials</th>
            <th className="p-3">Status</th>
            <th className="p-3">Latency</th>
            <th className="p-3">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800">
          {proxies.map((p) => (
            <tr key={p.id} className="hover:bg-zinc-900/50">
              <td className="p-3">
                <input type="checkbox" checked={selected.has(p.id)} onChange={() => onToggleSelect(p.id)} />
              </td>
              <td className="p-3">
                <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs">{p.scheme}</span>
              </td>
              <td className="p-3 font-mono">{p.host}:{p.port}</td>
              <td className="p-3">
                {p.username ? (
                  <button onClick={() => toggleCreds(p.id)} className="text-zinc-400 hover:text-white">
                    {showCreds.has(p.id) ? `${p.username}:•••` : '👁 •••'}
                  </button>
                ) : '—'}
              </td>
              <td className="p-3">
                <span className={`rounded px-2 py-0.5 text-xs ${statusColors[p.status] || ''}`}>
                  {p.status}
                </span>
              </td>
              <td className="p-3">{p.latency_ms != null ? `${p.latency_ms}ms` : '—'}</td>
              <td className="p-3">
                <button onClick={() => onDelete(p.id)} className="text-red-400 hover:text-red-300">
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
