import { useEffect, useState } from 'react'
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
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { toast } from '@/components/ui/toast'

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

  useEffect(() => {
    if (data) {
      setValues(Object.fromEntries(data.items.map((item) => [item.key, String(item.value)])))
    }
  }, [data])

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
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-xs text-muted-foreground">
          Adjust health check behavior without editing .env. Changes apply from
          the next check cycle.
        </p>
      </div>
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Health Check</CardTitle>
          <CardDescription>
            Values are seeded from .env on first startup and can be overridden
            here at any time.
          </CardDescription>
        </CardHeader>
        {isPending ? (
          <CardContent>
            <div className="flex flex-col gap-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          </CardContent>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-(--card-spacing)">
            <CardContent>
              <FieldGroup className="gap-4">
                {data?.items.map((item) => (
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
        )}
      </Card>
    </div>
  )
}
