import { useEffect, useState } from 'react'
import type { ProxyItem } from '@/api/proxies'
import { updateProxy } from '@/api/proxies'
import { Button } from '@/components/ui/button'
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
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { toast } from '@/components/ui/toast'

const schemeItems = [
  { label: 'http', value: 'http' },
  { label: 'https', value: 'https' },
]

const statusItems = [
  { label: 'Alive', value: 'alive' },
  { label: 'Dead', value: 'dead' },
  { label: 'Unknown', value: 'unknown' },
]

interface Props {
  proxy: ProxyItem | null
  onOpenChange: (open: boolean) => void
  onUpdated: () => void
}

export function EditProxyDialog({ proxy, onOpenChange, onUpdated }: Props) {
  const [scheme, setScheme] = useState('http')
  const [host, setHost] = useState('')
  const [port, setPort] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [status, setStatus] = useState('unknown')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (proxy) {
      setScheme(proxy.scheme)
      setHost(proxy.host)
      setPort(String(proxy.port))
      setUsername(proxy.username ?? '')
      setPassword(proxy.password ?? '')
      setStatus(proxy.status)
      setError('')
    }
  }, [proxy])

  const handleOpenChange = (next: boolean) => {
    if (!next) setError('')
    onOpenChange(next)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!proxy) return
    setError('')
    setLoading(true)
    try {
      await updateProxy(proxy.id, {
        scheme,
        host,
        port: parseInt(port),
        username: username || null,
        password: password || null,
        status,
      })
      toast.add({ type: 'success', title: 'Proxy updated' })
      onUpdated()
      handleOpenChange(false)
    } catch (err: unknown) {
      const resp = (err as { response?: { status?: number; data?: { detail?: string } } })
        ?.response
      if (resp?.status === 404) {
        toast.add({ type: 'error', title: 'Proxy not found' })
        handleOpenChange(false)
      } else {
        setError(resp?.data?.detail || 'Failed to update proxy')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={proxy !== null} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Proxy</DialogTitle>
          <DialogDescription>
            Update proxy connection details and status.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
          <FieldGroup>
            <Field>
              <FieldLabel>Scheme</FieldLabel>
              <Select
                items={schemeItems}
                value={scheme}
                onValueChange={(value) => setScheme(value ?? 'http')}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {schemeItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <Field data-invalid={!!error}>
              <FieldLabel htmlFor="edit-proxy-host">Host</FieldLabel>
              <Input
                id="edit-proxy-host"
                placeholder="Host (e.g. 1.2.3.4)"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                aria-invalid={!!error}
                required
              />
              {error && <FieldDescription>{error}</FieldDescription>}
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-proxy-port">Port</FieldLabel>
              <Input
                id="edit-proxy-port"
                type="number"
                min={1}
                max={65535}
                placeholder="Port (e.g. 8080)"
                value={port}
                onChange={(e) => setPort(e.target.value)}
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-proxy-username">Username (optional)</FieldLabel>
              <Input
                id="edit-proxy-username"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="edit-proxy-password">Password (optional)</FieldLabel>
              <Input
                id="edit-proxy-password"
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel>Status</FieldLabel>
              <Select
                items={statusItems}
                value={status}
                onValueChange={(value) => setStatus(value ?? 'unknown')}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {statusItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => handleOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading && <Spinner data-icon="inline-start" />}
                Save
              </Button>
            </DialogFooter>
          </FieldGroup>
        </form>
      </DialogContent>
    </Dialog>
  )
}
