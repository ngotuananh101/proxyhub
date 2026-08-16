import { useEffect, useState } from 'react'
import { createSource, updateSource, type SourceItem } from '@/api/sources'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { toast } from '@/components/ui/toast'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => void
  source: SourceItem | null
}

export function SourceDialog({ open, onOpenChange, onSaved, source }: Props) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [interval, setInterval_] = useState('60')
  const [enabled, setEnabled] = useState(true)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      setName(source?.name ?? '')
      setUrl(source?.url ?? '')
      setInterval_(String(source?.interval_minutes ?? 60))
      setEnabled(source?.enabled ?? true)
      setError('')
    }
  }, [open, source])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    const data = {
      name,
      url,
      enabled,
      interval_minutes: parseInt(interval) || 60,
    }
    try {
      if (source) {
        await updateSource(source.id, data)
        toast.add({ type: 'success', title: 'Source updated' })
      } else {
        await createSource(data)
        toast.add({ type: 'success', title: 'Source added' })
      }
      onSaved()
      onOpenChange(false)
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || 'Failed to save source'
      setError(typeof detail === 'string' ? detail : 'Failed to save source')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{source ? 'Edit Source' : 'Add Source'}</DialogTitle>
          <DialogDescription>
            A plain-text proxy list URL, one proxy per line (ip:port or
            scheme://ip:port). New proxies are imported as unknown.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <FieldGroup>
            <Field data-invalid={!!error}>
              <FieldLabel htmlFor="source-name">Name</FieldLabel>
              <Input
                id="source-name"
                placeholder="e.g. monosans/proxy-list"
                value={name}
                onChange={(e) => setName(e.target.value)}
                aria-invalid={!!error}
                required
              />
            </Field>
            <Field data-invalid={!!error}>
              <FieldLabel htmlFor="source-url">URL (txt)</FieldLabel>
              <Input
                id="source-url"
                type="url"
                placeholder="https://example.com/proxies.txt"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                aria-invalid={!!error}
                required
              />
              {error && <FieldDescription>{error}</FieldDescription>}
            </Field>
            <Field>
              <FieldLabel htmlFor="source-interval">Update interval (minutes)</FieldLabel>
              <Input
                id="source-interval"
                type="number"
                min={1}
                max={10080}
                value={interval}
                onChange={(e) => setInterval_(e.target.value)}
                required
              />
              <FieldDescription>How often this source is fetched automatically.</FieldDescription>
            </Field>
            <Field orientation="horizontal">
              <Checkbox
                id="source-enabled"
                checked={enabled}
                onCheckedChange={(checked) => setEnabled(checked === true)}
              />
              <FieldLabel htmlFor="source-enabled">Enabled</FieldLabel>
            </Field>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading && <Spinner data-icon="inline-start" />}
                {source ? 'Save' : 'Add'}
              </Button>
            </DialogFooter>
          </FieldGroup>
        </form>
      </DialogContent>
    </Dialog>
  )
}
