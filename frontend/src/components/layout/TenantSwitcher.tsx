import { useNavigate } from 'react-router-dom'
import { Building2Icon, CheckIcon, ChevronsUpDownIcon, Settings2Icon } from 'lucide-react'
import { useTenant } from '@/lib/tenant'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { toast } from '@/components/ui/toast'

export function TenantSwitcher() {
  const navigate = useNavigate()
  const { activeTenant, availableTenants, setActiveTenant } = useTenant()

  if (!activeTenant && availableTenants.length === 0) {
    return null
  }

  const handleSelect = (tenant: typeof availableTenants[0]) => {
    if (tenant.id === activeTenant?.id) return
    setActiveTenant(tenant)
    toast.add({ type: 'success', title: `Switched to tenant: ${tenant.name}` })
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 border-dashed px-2.5 font-normal text-xs"
          />
        }
        aria-label="Select tenant"
      >
        <Building2Icon className="size-3.5 text-muted-foreground" />
        <span className="max-w-[120px] truncate font-medium text-foreground">
          {activeTenant?.name ?? 'Select tenant'}
        </span>
        <ChevronsUpDownIcon className="size-3 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-xs text-muted-foreground font-normal">
            Tenants
          </DropdownMenuLabel>
          {availableTenants.map((tenant) => {
            const isSelected = tenant.id === activeTenant?.id
            return (
              <DropdownMenuItem
                key={tenant.id}
                onClick={() => handleSelect(tenant)}
                className="flex items-center justify-between text-xs"
              >
                <div className="flex flex-col">
                  <span className="font-medium text-foreground">{tenant.name}</span>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {tenant.slug}
                  </span>
                </div>
                {isSelected && <CheckIcon className="size-3.5 text-primary" />}
              </DropdownMenuItem>
            )
          })}
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem
            onClick={() => navigate('/tenants')}
            className="text-xs text-muted-foreground"
          >
            <Settings2Icon className="size-3.5" />
            Manage tenants
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
