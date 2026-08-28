import { describe, it, expect, beforeEach, vi } from 'vitest'
import client from '../api/client'
import {
  listTenants,
  createTenant,
  listMembers,
  addMember,
  removeMember,
} from '../api/tenants'

describe('Tenant API and Client Interceptor', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('injects X-Tenant-Id header when selected_tenant_id is in localStorage', async () => {
    localStorage.setItem('selected_tenant_id', '42')
    const spy = vi.spyOn(client, 'get').mockResolvedValueOnce({ data: [] })

    await listTenants()

    expect(spy).toHaveBeenCalledWith('/api/tenants')
  })

  it('createTenant posts to /api/tenants', async () => {
    const mockTenant = { id: 1, name: 'Acme', slug: 'acme', created_at: '2026-01-01T00:00:00' }
    vi.spyOn(client, 'post').mockResolvedValueOnce({ data: mockTenant })

    const result = await createTenant({ name: 'Acme', slug: 'acme' })
    expect(result).toEqual(mockTenant)
    expect(client.post).toHaveBeenCalledWith('/api/tenants', { name: 'Acme', slug: 'acme' })
  })

  it('listMembers gets from /api/tenants/:id/members', async () => {
    const mockMembers = [{ id: 1, tenant_id: 1, user_id: 2, role: 'member' as const }]
    vi.spyOn(client, 'get').mockResolvedValueOnce({ data: mockMembers })

    const result = await listMembers(1)
    expect(result).toEqual(mockMembers)
    expect(client.get).toHaveBeenCalledWith('/api/tenants/1/members')
  })

  it('addMember posts to /api/tenants/:id/members', async () => {
    const mockMember = { id: 1, tenant_id: 1, user_id: 2, role: 'admin' as const }
    vi.spyOn(client, 'post').mockResolvedValueOnce({ data: mockMember })

    const result = await addMember(1, { user_id: 2, role: 'admin' })
    expect(result).toEqual(mockMember)
    expect(client.post).toHaveBeenCalledWith('/api/tenants/1/members', {
      user_id: 2,
      role: 'admin',
    })
  })

  it('removeMember deletes from /api/tenants/:id/members/:userId', async () => {
    vi.spyOn(client, 'delete').mockResolvedValueOnce({ data: null })

    await removeMember(1, 2)
    expect(client.delete).toHaveBeenCalledWith('/api/tenants/1/members/2')
  })
})
