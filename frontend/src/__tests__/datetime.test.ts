import { describe, expect, it } from 'vitest'
import { COMMON_TIMEZONES, formatDateTime, formatTime, listTimezones } from '@/lib/datetime'

describe('formatDateTime', () => {
  it('renders a UTC instant in the UTC zone', () => {
    expect(formatDateTime('2026-08-16T12:30:45+00:00', 'UTC')).toBe(
      'Aug 16, 2026, 12:30 PM'
    )
  })

  it('shifts the instant into another zone', () => {
    expect(formatDateTime('2026-08-16T12:30:45+00:00', 'Asia/Ho_Chi_Minh')).toBe(
      'Aug 16, 2026, 7:30 PM'
    )
  })

  it('falls back to local time for an unknown zone', () => {
    expect(formatDateTime('2026-08-16T12:30:45+00:00', 'Not/AZone')).not.toBe('—')
  })

  it('returns a dash for invalid input', () => {
    expect(formatDateTime('not-a-date')).toBe('—')
  })
})

describe('formatTime', () => {
  it('renders only the time part in the given zone', () => {
    expect(formatTime('2026-08-16T12:30:45+00:00', 'UTC')).toBe('12:30:45 PM')
  })
})

describe('COMMON_TIMEZONES', () => {
  it('surfaces a friendly Vietnam entry with its UTC offset', () => {
    const vietnam = COMMON_TIMEZONES.find((z) => z.value === 'Asia/Ho_Chi_Minh')
    expect(vietnam).toBeDefined()
    expect(vietnam?.label).toContain('Vietnam')
    expect(vietnam?.label).toContain('GMT+07:00')
  })

  it('keeps UTC at a friendly position', () => {
    expect(
      COMMON_TIMEZONES.find((z) => z.value === 'UTC')?.label
    ).toContain('Coordinated Universal Time')
  })
})

describe('listTimezones', () => {
  it('includes common zones', () => {
    const zones = listTimezones()
    expect(zones).toContain('UTC')
    expect(zones).toContain('America/New_York')
    expect(zones).toContain('Europe/London')
  })
})
