import { useState } from 'react'
import { importProxies, type ImportResult } from '../api/proxies'

interface Props {
  open: boolean
  onClose: () => void
  onImported: () => void
}

export default function ImportDialog({ open, onClose, onImported }: Props) {
  const [text, setText] = useState('')
  const [result, setResult] = useState<ImportResult | null>(null)
  const [loading, setLoading] = useState(false)

  if (!open) return null

  const handleImport = async () => {
    setLoading(true)
    try {
      const res = await importProxies(text)
      setResult(res)
      onImported()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-lg rounded-lg border border-zinc-700 bg-zinc-900 p-6">
        <h2 className="mb-4 text-lg font-bold text-white">Import Proxies</h2>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"http://user:pass@1.2.3.4:8080\nsocks5://5.6.7.8:1080"}
          className="h-40 w-full rounded border border-zinc-700 bg-zinc-800 p-3 font-mono text-sm text-white"
        />
        {result && (
          <div className="mt-3 text-sm">
            <p className="text-green-400">Imported: {result.imported}</p>
            <p className="text-yellow-400">Duplicates: {result.duplicates}</p>
            {result.invalid.length > 0 && (
              <div className="text-red-400">
                <p>Invalid ({result.invalid.length}):</p>
                {result.invalid.map((inv, i) => (
                  <p key={i} className="ml-2 font-mono text-xs">{inv.line} — {inv.reason}</p>
                ))}
              </div>
            )}
          </div>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="rounded px-4 py-2 text-zinc-400 hover:text-white">Close</button>
          <button
            onClick={handleImport}
            disabled={loading || !text.trim()}
            className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Importing...' : 'Import'}
          </button>
        </div>
      </div>
    </div>
  )
}
