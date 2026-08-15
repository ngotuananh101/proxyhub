import { useState } from 'react'
import { importProxies, type ImportResult } from '@/api/proxies'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/toast'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onImported: () => void
}

export function ImportDialog({ open, onOpenChange, onImported }: Props) {
  const [text, setText] = useState('')
  const [result, setResult] = useState<ImportResult | null>(null)
  const [loading, setLoading] = useState(false)

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setText('')
      setResult(null)
    }
    onOpenChange(next)
  }

  const handleImport = async () => {
    setLoading(true)
    try {
      const res = await importProxies(text)
      setResult(res)
      onImported()
      toast.add({
        type: 'success',
        title: `Đã import ${res.imported} proxy`,
        description:
          res.duplicates > 0 ? `${res.duplicates} trùng lặp` : undefined,
      })
    } catch {
      toast.add({ type: 'error', title: 'Import thất bại' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import Proxies</DialogTitle>
          <DialogDescription>
            Nhập danh sách proxy, mỗi dòng một proxy.
          </DialogDescription>
        </DialogHeader>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="import-text" className="sr-only">
              Proxy list
            </FieldLabel>
            <Textarea
              id="import-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={'http://user:pass@1.2.3.4:8080\nsocks5://5.6.7.8:1080'}
              className="h-40 font-mono text-xs"
            />
          </Field>
          {result && (
            <div className="flex flex-col gap-1 text-sm">
              <p>
                Imported: <span className="font-medium">{result.imported}</span>
                {' · '}Duplicates:{' '}
                <span className="font-medium">{result.duplicates}</span>
              </p>
              {result.invalid.length > 0 && (
                <div className="flex flex-col gap-0.5">
                  <p className="text-destructive">
                    Invalid ({result.invalid.length}):
                  </p>
                  {result.invalid.map((inv, i) => (
                    <p key={i} className="font-mono text-xs text-muted-foreground">
                      {inv.line} — {inv.reason}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}
        </FieldGroup>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Close
          </Button>
          <Button onClick={handleImport} disabled={loading || !text.trim()}>
            {loading && <Spinner data-icon="inline-start" />}
            Import
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
