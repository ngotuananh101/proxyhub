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
const SOURCE_KEYS = new Set(['SOURCE_FETCH_TIMEOUT', 'DEAD_PROXY_RETENTION_DAYS'])

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

function GeneralSettingsForm({ item }: { item: SettingItem }) {
  const queryClient = useQueryClient()
  const [value, setValue] = useState(String(item.value))
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const timezones = useMemo(() => listTimezones(), [])

  useEffect(() => {
    setValue(String(item.value))
  }, [item.value])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      await updateSettings({ [TIMEZONE_KEY]: value })
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      toast.add({ type: 'success', title: 'General settings saved' })
    } catch (err) {
      setError(errorDetail(err, 'Failed to save general settings'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>General</CardTitle>
        <CardDescription>
          Applies to every date and time shown in the dashboard.
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit} className="flex flex-col gap-(--card-spacing)">
        <CardContent>
          <FieldGroup className="gap-4">
            <Field data-invalid={!!error}>
              <FieldLabel htmlFor={`setting-${TIMEZONE_KEY}`}>
                {item.label}
              </FieldLabel>
              <Select
                value={value}
                onValueChange={(val) => {
                  if (val === null) return
                  setValue(val)
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
              <FieldDescription>{item.description}</FieldDescription>
            </Field>
          </FieldGroup>
        </CardContent>
        <CardFooter className="flex items-center justify-between">
          <p className="text-sm text-destructive">{error}</p>
          <Button type="submit" disabled={saving}>
            {saving && <Spinner data-icon="inline-start" />}
            Save changes
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}

function SourceSettingsForm({ items }: { items: SettingItem[] }) {
  const queryClient = useQueryClient()
  const [values, setValues] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setValues(Object.fromEntries(items.map((item) => [item.key, String(item.value)])))
  }, [items])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      await updateSettings(values)
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      toast.add({ type: 'success', title: 'Sources settings saved' })
    } catch (err) {
      setError(errorDetail(err, 'Failed to save sources settings'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sources &amp; Retention</CardTitle>
        <CardDescription>
          Configure source fetching timeouts and automatic dead proxy cleanup.
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit} className="flex flex-col gap-(--card-spacing)">
        <CardContent>
          <FieldGroup className="gap-4">
            {items.map((item) => (
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
      </form>
    </Card>
  )
}

function HealthCheckSettingsForm({ items }: { items: SettingItem[] }) {
  const queryClient = useQueryClient()
  const [values, setValues] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setValues(Object.fromEntries(items.map((item) => [item.key, String(item.value)])))
  }, [items])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      await updateSettings(values)
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      toast.add({ type: 'success', title: 'Health check settings saved' })
    } catch (err) {
      setError(errorDetail(err, 'Failed to save health check settings'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Health Check</CardTitle>
        <CardDescription>
          Values are seeded from .env on first startup and can be overridden
          here at any time.
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit} className="flex flex-col gap-(--card-spacing)">
        <CardContent>
          <FieldGroup className="gap-4">
            {items.map((item) => (
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
      </form>
    </Card>
  )
}

export default function SettingsPage() {
  const { data, isPending } = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  })

  const timezoneItem = data?.items.find((item) => item.key === TIMEZONE_KEY)
  const sourceItems = data?.items.filter((item) => SOURCE_KEYS.has(item.key))
  const healthCheckItems = data?.items.filter(
    (item) => item.key !== TIMEZONE_KEY && !SOURCE_KEYS.has(item.key)
  )

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-4 p-1 pb-6">
        <div>
          <h1 className="text-xl font-semibold">Settings</h1>
          <p className="text-xs text-muted-foreground">
            Adjust health check behavior without editing .env. Changes apply from
            the next check cycle.
          </p>
        </div>
        {isPending ? (
          <div className="grid gap-6 lg:grid-cols-2 items-start">
            <div className="flex flex-col gap-6">
              <Card>
                <CardContent className="pt-6">
                  <div className="flex flex-col gap-4">
                    <Skeleton className="h-9 w-full" />
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-6">
                  <div className="flex flex-col gap-4">
                    {Array.from({ length: 2 }).map((_, i) => (
                      <Skeleton key={i} className="h-9 w-full" />
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
            <Card>
              <CardContent className="pt-6">
                <div className="flex flex-col gap-4">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-9 w-full" />
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        ) : (
          <div className="grid gap-6 lg:grid-cols-2 items-start">
            <div className="flex flex-col gap-6">
              {timezoneItem && <GeneralSettingsForm item={timezoneItem} />}
              {sourceItems && sourceItems.length > 0 && (
                <SourceSettingsForm items={sourceItems} />
              )}
            </div>
            {healthCheckItems && healthCheckItems.length > 0 && (
              <HealthCheckSettingsForm items={healthCheckItems} />
            )}
          </div>
        )}
      </div>
    </ScrollArea>
  )
}
