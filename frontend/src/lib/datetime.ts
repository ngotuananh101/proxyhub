function toDate(value: string): Date | null {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatter(
  timeZone: string | undefined,
  options: Intl.DateTimeFormatOptions
): Intl.DateTimeFormat {
  try {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone })
  } catch {
    // Unknown zone (e.g. a stale stored value) — fall back to browser time
    return new Intl.DateTimeFormat(undefined, options)
  }
}

/** Format an ISO timestamp as date + time in the given IANA timezone. */
export function formatDateTime(value: string, timeZone?: string): string {
  const date = toDate(value)
  if (!date) return '—'
  return formatter(timeZone, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

/** Format an ISO timestamp as time only in the given IANA timezone. */
export function formatTime(value: string, timeZone?: string): string {
  const date = toDate(value)
  if (!date) return '—'
  return formatter(timeZone, { timeStyle: 'medium' }).format(date)
}

/** IANA timezone names supported by the runtime, for the settings dropdown. */
export function listTimezones(): string[] {
  if (typeof Intl.supportedValuesOf !== 'function') return []
  const zones = Intl.supportedValuesOf('timeZone')
  // Some ICU builds omit the bare "UTC" alias; it is the default value, so
  // make sure it is always selectable.
  return zones.includes('UTC') ? zones : ['UTC', ...zones]
}
