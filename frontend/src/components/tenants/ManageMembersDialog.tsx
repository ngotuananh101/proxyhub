import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { addMember, listMembers, removeMember, type TenantItem } from '@/api/tenants'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { toast } from '@/components/ui/toast'
import { Trash2Icon, UserPlusIcon } from 'lucide-react'

interface ManageMembersDialogProps {
  tenant: TenantItem | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ManageMembersDialog({ tenant, open, onOpenChange }: ManageMembersDialogProps) {
  const queryClient = useQueryClient()
  const [userId, setUserId] = useState('')
  const [role, setRole] = useState<'member' | 'admin'>('member')

  const { data: members = [], isLoading } = useQuery({
    queryKey: ['tenant-members', tenant?.id],
    queryFn: () => (tenant ? listMembers(tenant.id) : Promise.resolve([])),
    enabled: open && !!tenant,
  })

  const addMutation = useMutation({
    mutationFn: () => {
      if (!tenant) throw new Error('No tenant')
      return addMember(tenant.id, { user_id: parseInt(userId, 10), role })
    },
    onSuccess: () => {
      toast.add({ type: 'success', title: 'Member added' })
      queryClient.invalidateQueries({ queryKey: ['tenant-members', tenant?.id] })
      setUserId('')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.add({ type: 'error', title: msg || 'Failed to add member' })
    },
  })

  const removeMutation = useMutation({
    mutationFn: (targetUserId: number) => {
      if (!tenant) throw new Error('No tenant')
      return removeMember(tenant.id, targetUserId)
    },
    onSuccess: () => {
      toast.add({ type: 'success', title: 'Member removed' })
      queryClient.invalidateQueries({ queryKey: ['tenant-members', tenant?.id] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.add({ type: 'error', title: msg || 'Failed to remove member' })
    },
  })

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault()
    if (!userId.trim()) return
    addMutation.mutate()
  }

  if (!tenant) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Manage Members — {tenant.name}</DialogTitle>
          <DialogDescription>
            Add or remove user memberships for tenant <code className="font-mono text-xs">{tenant.slug}</code>.
          </DialogDescription>
        </DialogHeader>

        {/* Add member form */}
        <form onSubmit={handleAdd} className="flex items-end gap-2 border-b pb-4">
          <Field className="flex-1">
            <FieldLabel htmlFor="user-id">User ID</FieldLabel>
            <Input
              id="user-id"
              type="number"
              placeholder="e.g. 2"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              required
            />
          </Field>
          <Field className="w-32">
            <FieldLabel htmlFor="member-role">Role</FieldLabel>
            <Select value={role} onValueChange={(val) => setRole(val as 'member' | 'admin')}>
              <SelectTrigger id="member-role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="member">Member</SelectItem>
                <SelectItem value="admin">Admin</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Button type="submit" size="default" disabled={addMutation.isPending || !userId.trim()}>
            <UserPlusIcon className="size-4 mr-1" />
            Add
          </Button>
        </form>

        {/* Members table */}
        <div className="max-h-[300px] overflow-y-auto">
          {isLoading ? (
            <p className="py-4 text-center text-xs text-muted-foreground">Loading members...</p>
          ) : members.length === 0 ? (
            <p className="py-4 text-center text-xs text-muted-foreground">No members assigned yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User ID</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead className="w-[80px] text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="font-mono text-xs">User #{m.user_id}</TableCell>
                    <TableCell>
                      <Badge variant={m.role === 'admin' ? 'default' : 'secondary'} className="text-[10px]">
                        {m.role}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-7 text-destructive hover:bg-destructive/10"
                        onClick={() => removeMutation.mutate(m.user_id)}
                        disabled={removeMutation.isPending}
                        aria-label={`Remove user ${m.user_id}`}
                      >
                        <Trash2Icon className="size-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
