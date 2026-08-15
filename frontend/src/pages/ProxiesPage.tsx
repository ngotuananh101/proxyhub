import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchProxies, deleteProxy, deleteManyProxies } from '../api/proxies'
import StatCards from '../components/StatCards'
import ProxyTable from '../components/ProxyTable'
import ImportDialog from '../components/ImportDialog'
import ProxyForm from '../components/ProxyForm'

export default function ProxiesPage() {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [showImport, setShowImport] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const queryClient = useQueryClient()

  const { data } = useQuery({
    queryKey: ['proxies', page, statusFilter, search],
    queryFn: () => fetchProxies({ page, status: statusFilter || undefined, q: search || undefined }),
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['proxies'] })
    queryClient.invalidateQueries({ queryKey: ['stats'] })
  }

  const handleDelete = async (id: number) => {
    await deleteProxy(id)
    setSelected((prev) => { const n = new Set(prev); n.delete(id); return n })
    invalidate()
  }

  const handleDeleteSelected = async () => {
    await deleteManyProxies([...selected])
    setSelected(new Set())
    invalidate()
  }

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
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
    <div className="min-h-screen bg-zinc-950 p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-white">ProxyHub</h1>
          <div className="flex gap-2">
            <button onClick={() => setShowForm(true)} className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700">Add Proxy</button>
            <button onClick={() => setShowImport(true)} className="rounded bg-zinc-700 px-4 py-2 text-sm text-white hover:bg-zinc-600">Import</button>
            {selected.size > 0 && (
              <button onClick={handleDeleteSelected} className="rounded bg-red-700 px-4 py-2 text-sm text-white hover:bg-red-600">
                Delete ({selected.size})
              </button>
            )}
          </div>
        </div>

        <StatCards />

        <div className="flex gap-3">
          <input
            placeholder="Search host..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            className="rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white"
          />
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
            className="rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white"
          >
            <option value="">All</option>
            <option value="alive">Alive</option>
            <option value="dead">Dead</option>
            <option value="unknown">Unknown</option>
          </select>
        </div>

        {data && (
          <>
            <ProxyTable
              proxies={data.items}
              selected={selected}
              onToggleSelect={toggleSelect}
              onToggleSelectAll={toggleSelectAll}
              onDelete={handleDelete}
            />
            <div className="flex items-center justify-between text-sm text-zinc-400">
              <span>Page {data.page} — {data.total} total</span>
              <div className="flex gap-2">
                <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded border border-zinc-700 px-3 py-1 disabled:opacity-30">Prev</button>
                <button disabled={page * data.size >= data.total} onClick={() => setPage(page + 1)} className="rounded border border-zinc-700 px-3 py-1 disabled:opacity-30">Next</button>
              </div>
            </div>
          </>
        )}
      </div>

      <ImportDialog open={showImport} onClose={() => setShowImport(false)} onImported={invalidate} />
      <ProxyForm open={showForm} onClose={() => setShowForm(false)} onCreated={invalidate} />
    </div>
  )
}
