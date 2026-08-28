import client from './client'

export interface TenantItem {
  id: number
  name: string
  slug: string
  created_at: string
}

export interface TenantCreateInput {
  name: string
  slug?: string
}

export interface TenantMembershipItem {
  id: number
  tenant_id: number
  user_id: number
  role: 'admin' | 'member'
}

export interface MembershipCreateInput {
  user_id: number
  role: string
}

export async function listTenants(): Promise<TenantItem[]> {
  const res = await client.get<TenantItem[]>('/api/tenants')
  return res.data
}

export async function createTenant(input: TenantCreateInput): Promise<TenantItem> {
  const res = await client.post<TenantItem>('/api/tenants', input)
  return res.data
}

export async function listMembers(tenantId: number): Promise<TenantMembershipItem[]> {
  const res = await client.get<TenantMembershipItem[]>(`/api/tenants/${tenantId}/members`)
  return res.data
}

export async function addMember(
  tenantId: number,
  input: MembershipCreateInput
): Promise<TenantMembershipItem> {
  const res = await client.post<TenantMembershipItem>(`/api/tenants/${tenantId}/members`, input)
  return res.data
}

export async function removeMember(tenantId: number, userId: number): Promise<void> {
  await client.delete(`/api/tenants/${tenantId}/members/${userId}`)
}
