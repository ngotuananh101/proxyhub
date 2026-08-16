import client from './client'

export interface SourceItem {
  id: number
  name: string
  url: string
  enabled: boolean
  interval_minutes: number
  last_fetched_at: string | null
  last_status: string | null
  created_at: string
}

export interface SourceInput {
  name: string
  url: string
  enabled: boolean
  interval_minutes: number
}

export async function fetchSources(): Promise<SourceItem[]> {
  const res = await client.get('/api/sources')
  return res.data
}

export async function createSource(data: SourceInput): Promise<SourceItem> {
  const res = await client.post('/api/sources', data)
  return res.data
}

export async function updateSource(
  id: number,
  data: Partial<SourceInput>
): Promise<SourceItem> {
  const res = await client.put(`/api/sources/${id}`, data)
  return res.data
}

export async function deleteSource(id: number): Promise<void> {
  await client.delete(`/api/sources/${id}`)
}

export async function fetchSourceNow(id: number): Promise<{ detail: string; status: string }> {
  const res = await client.post(`/api/sources/${id}/fetch`)
  return res.data
}
