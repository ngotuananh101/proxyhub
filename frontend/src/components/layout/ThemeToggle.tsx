import { MonitorIcon, MoonIcon, SunIcon } from 'lucide-react'
import { useTheme, type Theme } from '@/lib/theme'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const themeIcons: Record<Theme, typeof SunIcon> = {
  light: SunIcon,
  dark: MoonIcon,
  system: MonitorIcon,
}

const themeOptions: { value: Theme; label: string; icon: typeof SunIcon }[] = [
  { value: 'light', label: 'Light', icon: SunIcon },
  { value: 'dark', label: 'Dark', icon: MoonIcon },
  { value: 'system', label: 'System', icon: MonitorIcon },
]

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const Icon = themeIcons[theme]

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="ghost" size="icon" className="size-8" />}
        aria-label="Toggle theme"
      >
        <Icon />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Theme</DropdownMenuLabel>
          <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
            {themeOptions.map((option) => (
              <DropdownMenuRadioItem key={option.value} value={option.value}>
                <option.icon />
                {option.label}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
