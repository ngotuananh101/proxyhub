import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import LoginPage from '../pages/LoginPage'
import * as authApi from '../api/auth'

vi.mock('../api/auth')

describe('LoginPage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows error on failed login', async () => {
    vi.mocked(authApi.login).mockRejectedValue(new Error('401'))
    render(<MemoryRouter><LoginPage /></MemoryRouter>)

    fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText('Invalid username or password')).toBeInTheDocument()
    })
  })

  it('stores token on successful login', async () => {
    vi.mocked(authApi.login).mockResolvedValue({ access_token: 'tok123', token_type: 'bearer' })
    render(<MemoryRouter><LoginPage /></MemoryRouter>)

    fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'pass' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(localStorage.getItem('access_token')).toBe('tok123')
    })
  })
})
