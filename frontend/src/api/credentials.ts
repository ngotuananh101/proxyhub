import client from './client'

export interface CredentialItem {
  id: number
  tenant_id: number
  name: string
  auth_mode: 'basic' | 'ip_whitelist'
  username: string | null
  cidrs: string | null
  is_active: boolean
  last_used_at: string | null
  created_at: string
}

export interface CredentialListResponse {
  items: CredentialItem[]
  total: number
}

export interface CreateCredentialPayload {
  name: string
  auth_mode: 'basic' | 'ip_whitelist'
  username?: string
  cidrs?: string
}

export interface CreatedCredentialResponse extends CredentialItem {
  generated_password?: string | null
}

export interface UpdateCredentialPayload {
  name?: string
  is_active?: boolean
  cidrs?: string
  rotate_password?: boolean
}

export async function fetchCredentials(): Promise<CredentialListResponse> {
  const res = await client.get('/api/gateway-credentials')
  return res.data
}

export async function createCredential(
  payload: CreateCredentialPayload
): Promise<CreatedCredentialResponse> {
  const res = await client.post('/api/gateway-credentials', payload)
  return res.data
}

export async function updateCredential(
  id: number,
  payload: UpdateCredentialPayload
): Promise<CreatedCredentialResponse> {
  const res = await client.patch(`/api/gateway-credentials/${id}`, payload)
  return res.data
}

export async function deleteCredential(id: number): Promise<void> {
  await client.delete(`/api/gateway-credentials/${id}`)
}
