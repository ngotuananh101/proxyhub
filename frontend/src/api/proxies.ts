import client from './client'

export interface ProxyItem {
  id: number
  scheme: string
  host: string
  port: number
  username: string | null
  password: string | null
  status: string
  latency_ms: number | null
  last_checked_at: string | null
  created_at: string
  updated_at: string
}

export interface ProxyListResponse {
  items: ProxyItem[]
  total: number
  page: number
  size: number
}

export interface ImportResult {
  imported: number
  duplicates: number
  invalid: { line: string; reason: string }[]
}

export interface StatsSummary {
  total: number
  alive: number
  dead: number
  unknown: number
}

export async function fetchProxies(params?: {
  page?: number; size?: number; status?: string; q?: string
}): Promise<ProxyListResponse> {
  const res = await client.get('/api/proxies', { params })
  return res.data
}

export async function createProxy(data: {
  scheme: string; host: string; port: number; username?: string; password?: string
}): Promise<ProxyItem> {
  const res = await client.post('/api/proxies', data)
  return res.data
}

export async function importProxies(text: string): Promise<ImportResult> {
  const res = await client.post('/api/proxies/import', { text })
  return res.data
}

export async function deleteProxy(id: number): Promise<void> {
  await client.delete(`/api/proxies/${id}`)
}

export async function deleteManyProxies(ids: number[]): Promise<void> {
  await client.delete('/api/proxies', { data: { ids } })
}

export async function fetchStats(): Promise<StatsSummary> {
  const res = await client.get('/api/stats/summary')
  return res.data
}

export interface CheckAllResponse {
  detail: string
  task_id: string
}

export async function triggerCheckAll(): Promise<CheckAllResponse> {
  const res = await client.post('/api/proxies/check-all')
  return res.data
}

export async function clearDeadProxies(): Promise<{ deleted: number }> {
  const res = await client.post('/api/proxies/clear-dead')
  return res.data
}

