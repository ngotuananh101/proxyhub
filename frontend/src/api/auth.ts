import client from './client'

export interface LoginResponse {
  access_token: string
  token_type: string
}

export interface UserResponse {
  id: number
  username: string
  email: string | null
  is_admin: boolean
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const res = await client.post<LoginResponse>('/api/auth/login', { username, password })
  return res.data
}

export async function getMe(): Promise<UserResponse> {
  const res = await client.get<UserResponse>('/api/auth/me')
  return res.data
}
