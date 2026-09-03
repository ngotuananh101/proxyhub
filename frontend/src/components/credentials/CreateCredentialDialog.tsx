import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { createCredential, type CreatedCredentialResponse } from '@/api/credentials'
import { toast } from '@/components/ui/toast'

interface CreateCredentialDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccessCreated: (resp: CreatedCredentialResponse) => void
}

export function CreateCredentialDialog({
  open,
  onOpenChange,
  onSuccessCreated,
}: CreateCredentialDialogProps) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [authMode, setAuthMode] = useState<'basic' | 'ip_whitelist'>('basic')
  const [username, setUsername] = useState('')
  const [cidrs, setCidrs] = useState('')

  const mutation = useMutation({
    mutationFn: createCredential,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['gateway-credentials'] })
      toast.add({ type: 'success', title: `Credential '${data.name}' created` })
      onOpenChange(false)
      setName('')
      setUsername('')
      setCidrs('')
      onSuccessCreated(data)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.add({
        type: 'error',
        title: msg || 'Failed to create credential',
      })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    mutation.mutate({
      name,
      auth_mode: authMode,
      username: authMode === 'basic' ? username : undefined,
      cidrs: authMode === 'ip_whitelist' ? cidrs : undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Add Gateway Credential</DialogTitle>
            <DialogDescription>
              Create credentials for client access to the gateway port.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="cred-name">Name</Label>
              <Input
                id="cred-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Scraper Bot or Office Network"
                required
              />
            </div>

            <div className="space-y-2">
              <Label>Authentication Type</Label>
              <div className="flex gap-4 pt-1">
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="radio"
                    name="auth_mode"
                    value="basic"
                    checked={authMode === 'basic'}
                    onChange={() => setAuthMode('basic')}
                    className="size-4 text-primary focus:ring-primary border-input"
                  />
                  Basic Auth
                </label>
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="radio"
                    name="auth_mode"
                    value="ip_whitelist"
                    checked={authMode === 'ip_whitelist'}
                    onChange={() => setAuthMode('ip_whitelist')}
                    className="size-4 text-primary focus:ring-primary border-input"
                  />
                  IP Whitelist
                </label>
              </div>
            </div>

            {authMode === 'basic' ? (
              <div className="space-y-2">
                <Label htmlFor="cred-username">Username</Label>
                <Input
                  id="cred-username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. crawler1"
                  required
                />
                <p className="text-xs text-muted-foreground">
                  A strong password will be generated automatically.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="cred-cidrs">Allowed IPs / CIDRs</Label>
                <Textarea
                  id="cred-cidrs"
                  value={cidrs}
                  onChange={(e) => setCidrs(e.target.value)}
                  placeholder="192.168.1.0/24&#10;10.0.0.1"
                  rows={3}
                  required
                />
                <p className="text-xs text-muted-foreground">
                  Enter one IP or CIDR per line or comma-separated.
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
