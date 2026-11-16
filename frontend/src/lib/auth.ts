export function getToken(): string | null {
  return localStorage.getItem('access_token')
}

export function setToken(token: string): void {
  localStorage.setItem('access_token', token)
}

/**
 * Drop everything tied to the current login. The tenant selection must go too:
 * it is persisted, so leaving it behind means the next user to sign in on this
 * browser starts in whatever tenant the previous one had picked.
 */
export function clearSession(): void {
  localStorage.removeItem('access_token')
  localStorage.removeItem('selected_tenant_id')
}

export function isAuthenticated(): boolean {
  return !!getToken()
}
