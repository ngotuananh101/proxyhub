import { useState } from 'react'
import { createProxy } from '../api/proxies'

interface Props {
  open: boolean
  onClose: () => void
  onCreated: () => void
}

export default function ProxyForm({ open, onClose, onCreated }: Props) {
  const [scheme, setScheme] = useState('http')
  const [host, setHost] = useState('')
  const [port, setPort] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (!open) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await createProxy({
        scheme,
        host,
        port: parseInt(port),
        username: username || undefined,
        password: password || undefined,
      })
      onCreated()
      onClose()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create proxy')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <form onSubmit={handleSubmit} className="w-full max-w-md space-y-3 rounded-lg border border-zinc-700 bg-zinc-900 p-6">
        <h2 className="text-lg font-bold text-white">Add Proxy</h2>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <select value={scheme} onChange={(e) => setScheme(e.target.value)} className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-white">
          <option value="http">http</option>
          <option value="https">https</option>
          <option value="socks5" disabled>socks5 (not supported via gateway)</option>
        </select>
        <input placeholder="Host (e.g. 1.2.3.4)" value={host} onChange={(e) => setHost(e.target.value)} required className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-white" />
        <input placeholder="Port (e.g. 8080)" value={port} onChange={(e) => setPort(e.target.value)} required type="number" className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-white" />
        <input placeholder="Username (optional)" value={username} onChange={(e) => setUsername(e.target.value)} className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-white" />
        <input placeholder="Password (optional)" value={password} onChange={(e) => setPassword(e.target.value)} type="password" className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-white" />
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded px-4 py-2 text-zinc-400 hover:text-white">Cancel</button>
          <button type="submit" disabled={loading} className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50">
            {loading ? 'Adding...' : 'Add'}
          </button>
        </div>
      </form>
    </div>
  )
}
