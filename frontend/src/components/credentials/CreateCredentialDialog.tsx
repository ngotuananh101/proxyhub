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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Textarea } from '@/components/ui/textarea'
import { createCredential, CreatedCredentialResponse } from '@/api/credentials'
import { useToast } from '@/components/ui/toast'

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
  const { toast } = useToast()
  const [name, setName] = useState('')
  const [authMode, setAuthMode] = useState<'basic' | 'ip_whitelist'>('basic')
  const [username, setUsername] = useState('')
  const [cidrs, setCidrs] = useState('')

  const mutation = useMutation({
    mutationFn: createCredential,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['gateway-credentials'] })
      onOpenChange(false)
      setName('')
      setUsername('')
      setCidrs('')
      onSuccessCreated(data)
    },
    onError: (err: any) => {
      toast({
        title: 'Failed to create credential',
        description: err.response?.data?.detail || 'An error occurred',
        variant: 'destructive',
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
              <RadioGroup
                value={authMode}
                onValueChange={(v) => setAuthMode(v as 'basic' | 'ip_whitelist')}
                className="flex gap-4"
              >
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="basic" id="r-basic" />
                  <Label htmlFor="r-basic">Basic Auth</Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="ip_whitelist" id="r-ip" />
                  <Label htmlFor="r-ip">IP Whitelist</Label>
                </div>
              </RadioGroup>
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
