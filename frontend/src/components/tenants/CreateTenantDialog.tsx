import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createTenant } from '@/api/tenants'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { toast } from '@/components/ui/toast'

interface CreateTenantDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateTenantDialog({ open, onOpenChange }: CreateTenantDialogProps) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')

  const createMutation = useMutation({
    mutationFn: createTenant,
    onSuccess: (tenant) => {
      toast.add({ type: 'success', title: `Tenant '${tenant.name}' created` })
      queryClient.invalidateQueries({ queryKey: ['tenants'] })
      setName('')
      setSlug('')
      onOpenChange(false)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.add({ type: 'error', title: msg || 'Failed to create tenant' })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    createMutation.mutate({
      name: name.trim(),
      slug: slug.trim() || undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Create Tenant</DialogTitle>
            <DialogDescription>
              Add a new isolated tenant workspace.
            </DialogDescription>
          </DialogHeader>
          <FieldGroup className="py-4">
            <Field>
              <FieldLabel htmlFor="tenant-name">Tenant Name</FieldLabel>
              <Input
                id="tenant-name"
                placeholder="e.g. Acme Corp"
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                  if (!slug || slug === name.toLowerCase().replace(/\s+/g, '-')) {
                    setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''))
                  }
                }}
                required
                autoFocus
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="tenant-slug">Slug</FieldLabel>
              <Input
                id="tenant-slug"
                placeholder="e.g. acme-corp"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
              />
              <FieldDescription>
                Unique identifier used for routing and URLs.
              </FieldDescription>
            </Field>
          </FieldGroup>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending || !name.trim()}>
              {createMutation.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
