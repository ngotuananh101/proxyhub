import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building2Icon, PlusIcon, UsersIcon, CheckIcon } from 'lucide-react'
import { listTenants, type TenantItem } from '@/api/tenants'
import { useTenant } from '@/lib/tenant'
import { useTimezone } from '@/hooks/use-timezone'
import { formatDateTime } from '@/lib/datetime'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { CreateTenantDialog } from '@/components/tenants/CreateTenantDialog'
import { ManageMembersDialog } from '@/components/tenants/ManageMembersDialog'

export default function TenantsPage() {
  const tz = useTimezone()
  const { activeTenant, setActiveTenant } = useTenant()
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedTenantForMembers, setSelectedTenantForMembers] = useState<TenantItem | null>(null)

  const { data: tenants = [], isLoading } = useQuery({
    queryKey: ['tenants'],
    queryFn: listTenants,
  })

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tenants</h1>
          <p className="text-sm text-muted-foreground">
            Manage isolated multi-tenant workspaces and member permissions.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <PlusIcon className="size-4 mr-1.5" />
          Create Tenant
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-medium">All Tenants</CardTitle>
          <CardDescription>
            Each tenant has its own isolated proxy pools, sources, request logs, and stats.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead>Created At</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-28" /></TableCell>
                    <TableCell className="text-right"><Skeleton className="h-8 w-24 ml-auto" /></TableCell>
                  </TableRow>
                ))
              ) : tenants.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="h-32 text-center text-muted-foreground">
                    No tenants found.
                  </TableCell>
                </TableRow>
              ) : (
                tenants.map((tenant) => {
                  const isActive = tenant.id === activeTenant?.id
                  return (
                    <TableRow key={tenant.id}>
                      <TableCell className="font-medium">
                        <div className="flex items-center gap-2">
                          <Building2Icon className="size-4 text-muted-foreground" />
                          <span>{tenant.name}</span>
                          {isActive && (
                            <Badge variant="outline" className="text-[10px] bg-primary/5 text-primary border-primary/20">
                              Active
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <code className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">
                          {tenant.slug}
                        </code>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDateTime(tenant.created_at, tz)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            variant={isActive ? 'secondary' : 'outline'}
                            size="sm"
                            className="h-8 text-xs gap-1"
                            onClick={() => setActiveTenant(tenant)}
                            disabled={isActive}
                          >
                            {isActive ? (
                              <>
                                <CheckIcon className="size-3 text-primary" />
                                Active
                              </>
                            ) : (
                              'Switch to'
                            )}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-8 text-xs gap-1"
                            onClick={() => setSelectedTenantForMembers(tenant)}
                          >
                            <UsersIcon className="size-3 text-muted-foreground" />
                            Members
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <CreateTenantDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
      />

      <ManageMembersDialog
        tenant={selectedTenantForMembers}
        open={!!selectedTenantForMembers}
        onOpenChange={(open) => {
          if (!open) setSelectedTenantForMembers(null)
        }}
      />
    </div>
  )
}
