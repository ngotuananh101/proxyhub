import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { LogOutIcon, UserIcon } from 'lucide-react'
import { getMe } from '@/api/auth'
import { clearToken } from '@/lib/auth'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
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
import { Separator } from '@/components/ui/separator'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { ThemeToggle } from './ThemeToggle'

export function AppHeader() {
  const navigate = useNavigate()
  const { data: user } = useQuery({ queryKey: ['me'], queryFn: getMe })

  const initials = (user?.username ?? '?').slice(0, 2).toUpperCase()

  const handleLogout = () => {
    clearToken()
    navigate('/login')
  }

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b bg-background px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="h-5" />
      {/* Left side intentionally blank — reserved for breadcrumbs/search */}
      <div className="flex-1" />
      <ThemeToggle />
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button variant="ghost" size="icon" className="size-8 rounded-full" />
          }
          aria-label="User menu"
        >
          <Avatar className="size-8">
            <AvatarFallback className="text-xs">{initials}</AvatarFallback>
          </Avatar>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuGroup>
            <DropdownMenuLabel>
              <div className="flex flex-col gap-0.5">
                <span className="truncate text-sm text-foreground">{user?.username}</span>
                {user?.email && (
                  <span className="truncate font-normal">{user.email}</span>
                )}
              </div>
            </DropdownMenuLabel>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuItem onClick={() => navigate('/profile')}>
              <UserIcon />
              Manage profile
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onClick={handleLogout}>
              <LogOutIcon />
              Log out
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}
