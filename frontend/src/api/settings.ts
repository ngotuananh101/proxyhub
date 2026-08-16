import client from './client'

export interface SettingItem {
  key: string
  label: string
  description: string
  type: 'string' | 'int' | 'float'
  default: string | number
  min: number | null
  max: number | null
  value: string | number
}

export interface SettingsResponse {
  items: SettingItem[]
}

export async function fetchSettings(): Promise<SettingsResponse> {
  const res = await client.get('/api/settings')
  return res.data
}

export async function updateSettings(
  values: Record<string, string>
): Promise<{ values: Record<string, string | number> }> {
  const res = await client.put('/api/settings', { values })
  return res.data
}
