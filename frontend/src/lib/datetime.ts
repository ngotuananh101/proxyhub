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

export interface TimezoneOption {
  value: string
  label: string
}

function longOffset(zone: string): string {
  try {
    const part = new Intl.DateTimeFormat('en', {
      timeZone: zone,
      timeZoneName: 'longOffset',
    })
      .formatToParts(new Date())
      .find((p) => p.type === 'timeZoneName')
    return part?.value ?? ''
  } catch {
    return ''
  }
}

// Vietnam is a single UTC+07:00 zone, so Hà Nội and Hồ Chí Minh share one
// entry. Asia/Ho_Chi_Minh is an alias of canonical Asia/Saigon; both resolve,
// but we surface the friendly name the user is looking for.
const CURATED_TIMEZONES: ReadonlyArray<readonly [string, string]> = [
  ['Asia/Ho_Chi_Minh', 'Vietnam — Hà Nội / Hồ Chí Minh'],
  ['UTC', 'UTC (Coordinated Universal Time)'],
  ['Asia/Bangkok', 'Thailand — Bangkok'],
  ['Asia/Jakarta', 'Indonesia — Jakarta'],
  ['Asia/Singapore', 'Singapore'],
  ['Asia/Shanghai', 'China — Shanghai / Beijing'],
  ['Asia/Hong_Kong', 'Hong Kong'],
  ['Asia/Tokyo', 'Japan — Tokyo'],
  ['Asia/Seoul', 'South Korea — Seoul'],
  ['Asia/Kolkata', 'India — Kolkata'],
  ['Asia/Dubai', 'United Arab Emirates — Dubai'],
  ['Asia/Karachi', 'Pakistan — Karachi'],
  ['Europe/London', 'United Kingdom — London'],
  ['Europe/Paris', 'France — Paris'],
  ['Europe/Berlin', 'Germany — Berlin'],
  ['Europe/Moscow', 'Russia — Moscow'],
  ['Africa/Cairo', 'Egypt — Cairo'],
  ['Africa/Johannesburg', 'South Africa — Johannesburg'],
  ['America/New_York', 'USA — New York (ET)'],
  ['America/Chicago', 'USA — Chicago (CT)'],
  ['America/Los_Angeles', 'USA — Los Angeles (PT)'],
  ['America/Sao_Paulo', 'Brazil — São Paulo'],
  ['America/Toronto', 'Canada — Toronto'],
  ['Australia/Sydney', 'Australia — Sydney'],
  ['Pacific/Auckland', 'New Zealand — Auckland'],
] as const

/** Curated, labeled zones shown at the top of the settings dropdown. */
export const COMMON_TIMEZONES: TimezoneOption[] = CURATED_TIMEZONES.map(
  ([value, label]) => {
    const offset = longOffset(value)
    return { value, label: offset ? `${label} (${offset})` : label }
  }
)
