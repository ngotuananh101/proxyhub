import client from './client'

export interface LogItem {
  id: number
  tenant_id?: number | null
  auth_credential_id?: number | null
  auth_status?: 'allowed' | 'denied' | null
  client_ip: string | null
  method: string | null
  host: string | null
  path: string | null
  proxy_host: string | null
  proxy_port: number | null
  response_bytes: number | null
  created_at: string
}

export interface LogListResponse {
  items: LogItem[]
  total: number
  page: number
  size: number
}

export async function fetchLogs(params?: {
  page?: number
  size?: number
  method?: string
  q?: string
  start?: string
  end?: string
}): Promise<LogListResponse> {
  const res = await client.get('/api/logs', { params })
  return res.data
}
