import client from './client'

export interface LogItem {
  id: number
  client_ip: string | null
  method: string | null
  host: string | null
  path: string | null
  proxy_host: string | null
  proxy_port: number | null
  response_bytes: number | null
  created_at: string
}

export async function fetchLogs(limit = 100): Promise<LogItem[]> {
  const res = await client.get('/api/logs', { params: { limit } })
  return res.data
}
