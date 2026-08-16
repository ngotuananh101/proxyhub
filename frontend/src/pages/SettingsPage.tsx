import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchSettings, updateSettings, type SettingItem } from '@/api/settings'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { toast } from '@/components/ui/toast'
import { COMMON_TIMEZONES, listTimezones } from '@/lib/datetime'

const TIMEZONE_KEY = 'TIMEZONE'

function errorDetail(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response
    ?.data?.detail
  return detail || fallback
}

function boundsHint(item: SettingItem): string {
  const parts: string[] = []
  if (item.min !== null) parts.push(`min ${item.min}`)
  if (item.max !== null) parts.push(`max ${item.max}`)
  return parts.length ? ` (${parts.join(', ')})` : ''
}

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const { data, isPending } = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  })
  const [values, setValues] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const timezones = useMemo(() => listTimezones(), [])

  useEffect(() => {
    if (data) {
      setValues(Object.fromEntries(data.items.map((item) => [item.key, String(item.value)])))
    }
  }, [data])

  const timezoneItem = data?.items.find((item) => item.key === TIMEZONE_KEY)
  const otherItems = data?.items.filter((item) => item.key !== TIMEZONE_KEY)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      await updateSettings(values)
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      toast.add({ type: 'success', title: 'Settings saved' })
    } catch (err) {
      setError(errorDetail(err, 'Failed to save settings'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-4">
        <div>
          <h1 className="text-xl font-semibold">Settings</h1>
          <p className="text-xs text-muted-foreground">
            Adjust health check behavior without editing .env. Changes apply from
            the next check cycle.
          </p>
        </div>
        {isPending ? (
          <Card className="max-w-2xl">
            <CardContent>
              <div className="flex flex-col gap-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-9 w-full" />
                ))}
              </div>
            </CardContent>
          </Card>
        ) : (
          <form onSubmit={handleSubmit} className="flex max-w-2xl flex-col gap-4">
            {timezoneItem && (
              <Card>
                <CardHeader>
                  <CardTitle>General</CardTitle>
                  <CardDescription>
                    Applies to every date and time shown in the dashboard.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <FieldGroup className="gap-4">
                    <Field data-invalid={!!error}>
                      <FieldLabel htmlFor={`setting-${TIMEZONE_KEY}`}>
                        {timezoneItem.label}
                      </FieldLabel>
                      <Select
                        value={values[TIMEZONE_KEY] ?? ''}
                        onValueChange={(value) => {
                          if (value === null) return
                          setValues((prev) => ({ ...prev, [TIMEZONE_KEY]: value }))
                        }}
                      >
                        <SelectTrigger
                          id={`setting-${TIMEZONE_KEY}`}
                          aria-invalid={!!error}
                          className="w-full"
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectGroup>
                            <SelectLabel>Common</SelectLabel>
                            {COMMON_TIMEZONES.map((zone) => (
                              <SelectItem key={zone.value} value={zone.value}>
                                {zone.label}
                              </SelectItem>
                            ))}
                          </SelectGroup>
                          <SelectGroup>
                            <SelectLabel>All timezones</SelectLabel>
                            {timezones.map((zone) => (
                              <SelectItem key={zone} value={zone}>
                                {zone}
                              </SelectItem>
                            ))}
                          </SelectGroup>
                        </SelectContent>
                      </Select>
                      <FieldDescription>{timezoneItem.description}</FieldDescription>
                    </Field>
                  </FieldGroup>
                </CardContent>
              </Card>
            )}
            <Card>
              <CardHeader>
                <CardTitle>Health Check</CardTitle>
                <CardDescription>
                  Values are seeded from .env on first startup and can be overridden
                  here at any time.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <FieldGroup className="gap-4">
                  {otherItems?.map((item) => (
                    <Field key={item.key} data-invalid={!!error}>
                      <FieldLabel htmlFor={`setting-${item.key}`}>{item.label}</FieldLabel>
                      <Input
                        id={`setting-${item.key}`}
                        type={item.type === 'string' ? 'text' : 'number'}
                        step={item.type === 'float' ? 'any' : undefined}
                        min={item.min ?? undefined}
                        max={item.max ?? undefined}
                        value={values[item.key] ?? ''}
                        onChange={(e) =>
                          setValues((prev) => ({ ...prev, [item.key]: e.target.value }))
                        }
                        aria-invalid={!!error}
                        required
                      />
                      <FieldDescription>
                        {item.description}
                        {boundsHint(item)}
                      </FieldDescription>
                    </Field>
                  ))}
                </FieldGroup>
              </CardContent>
              <CardFooter className="flex items-center justify-between">
                <p className="text-sm text-destructive">{error}</p>
                <Button type="submit" disabled={saving}>
                  {saving && <Spinner data-icon="inline-start" />}
                  Save changes
                </Button>
              </CardFooter>
            </Card>
          </form>
        )}
      </div>
    </ScrollArea>
  )
}
