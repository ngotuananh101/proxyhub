import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRoundIcon, PlusIcon, RefreshCwIcon, Trash2Icon } from 'lucide-react'
import {
  fetchCredentials,
  updateCredential,
  deleteCredential,
  CredentialItem,
  CreatedCredentialResponse,
} from '@/api/credentials'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { CreateCredentialDialog } from '@/components/credentials/CreateCredentialDialog'
import { OneTimePasswordDialog } from '@/components/credentials/OneTimePasswordDialog'
import { useTenant } from '@/lib/tenant'

export default function GatewayCredentialsPage() {
  const { currentTenant } = useTenant()
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [otpDialog, setOtpDialog] = useState<{ open: boolean; username?: string | null; password?: string | null }>({
    open: false,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['gateway-credentials', currentTenant?.id],
    queryFn: fetchCredentials,
  })

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      updateCredential(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['gateway-credentials'] }),
  })

  const rotateMutation = useMutation({
    mutationFn: (id: number) => updateCredential(id, { rotate_password: true }),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['gateway-credentials'] })
      setOtpDialog({ open: true, username: res.username, password: res.generated_password })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteCredential,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['gateway-credentials'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Gateway Credentials</h1>
          <p className="text-muted-foreground text-sm">
            Manage client authentication for gateway port 8899.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <PlusIcon className="mr-2 size-4" /> Add Credential
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <KeyRoundIcon className="size-4" /> Credentials List
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Identity / CIDR</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last Used</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-6 text-muted-foreground">
                    Loading credentials...
                  </TableCell>
                </TableRow>
              ) : !data?.items?.length ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-6 text-muted-foreground">
                    No gateway credentials found. Create one to authenticate gateway traffic.
                  </TableCell>
                </TableRow>
              ) : (
                data.items.map((cred: CredentialItem) => (
                  <TableRow key={cred.id}>
                    <TableCell className="font-medium">{cred.name}</TableCell>
                    <TableCell>
                      <Badge variant={cred.auth_mode === 'basic' ? 'default' : 'secondary'}>
                        {cred.auth_mode === 'basic' ? 'Basic' : 'IP Whitelist'}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {cred.auth_mode === 'basic' ? cred.username : cred.cidrs}
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={cred.is_active}
                        onCheckedChange={(checked) =>
                          toggleActiveMutation.mutate({ id: cred.id, is_active: checked })
                        }
                      />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {cred.last_used_at ? new Date(cred.last_used_at).toLocaleString() : 'Never'}
                    </TableCell>
                    <TableCell className="text-right space-x-1">
                      {cred.auth_mode === 'basic' && (
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Rotate Password"
                          onClick={() => rotateMutation.mutate(cred.id)}
                        >
                          <RefreshCwIcon className="size-4" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Delete"
                        onClick={() => {
                          if (confirm(`Delete credential "${cred.name}"?`)) {
                            deleteMutation.mutate(cred.id)
                          }
                        }}
                      >
                        <Trash2Icon className="size-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <CreateCredentialDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onSuccessCreated={(resp: CreatedCredentialResponse) => {
          if (resp.generated_password) {
            setOtpDialog({ open: true, username: resp.username, password: resp.generated_password })
          }
        }}
      />

      <OneTimePasswordDialog
        open={otpDialog.open}
        onOpenChange={(open) => setOtpDialog((prev) => ({ ...prev, open }))}
        username={otpDialog.username}
        password={otpDialog.password}
      />
    </div>
  )
}
