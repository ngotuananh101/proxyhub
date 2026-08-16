import { useQuery } from '@tanstack/react-query'
import { fetchSettings } from '@/api/settings'

/** The IANA timezone configured on the Settings page (TIMEZONE key). */
export function useTimezone(): string | undefined {
  const { data } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings })
  const item = data?.items.find((setting) => setting.key === 'TIMEZONE')
  return item ? String(item.value) : undefined
}
