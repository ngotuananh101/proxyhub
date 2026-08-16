import { useState } from 'react'
import { createProxy } from '@/api/proxies'
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

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}

export function AddProxyDialog({ open, onOpenChange, onCreated }: Props) {
  const [scheme, setScheme] = useState('http')
  const [host, setHost] = useState('')
  const [port, setPort] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const reset = () => {
    setScheme('http')
    setHost('')
    setPort('')
    setUsername('')
    setPassword('')
    setError('')
  }

  const handleOpenChange = (next: boolean) => {
    if (!next) reset()
    onOpenChange(next)
  }

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
      toast.add({ type: 'success', title: 'Proxy added' })
      onCreated()
      handleOpenChange(false)
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || 'Failed to create proxy'
      setError(detail)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Proxy</DialogTitle>
          <DialogDescription>
            Add a proxy to the pool. socks5 is not supported through the gateway.
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
              <FieldLabel htmlFor="proxy-host">Host</FieldLabel>
              <Input
                id="proxy-host"
                placeholder="Host (e.g. 1.2.3.4)"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                aria-invalid={!!error}
                required
              />
              {error && <FieldDescription>{error}</FieldDescription>}
            </Field>
            <Field>
              <FieldLabel htmlFor="proxy-port">Port</FieldLabel>
              <Input
                id="proxy-port"
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
              <FieldLabel htmlFor="proxy-username">Username (optional)</FieldLabel>
              <Input
                id="proxy-username"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="proxy-password">Password (optional)</FieldLabel>
              <Input
                id="proxy-password"
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
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
                Add
              </Button>
            </DialogFooter>
          </FieldGroup>
        </form>
      </DialogContent>
    </Dialog>
  )
}
