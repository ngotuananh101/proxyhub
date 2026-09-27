import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, beforeEach } from 'vitest'
import { useLocalStorage } from '../hooks/use-local-storage'

describe('useLocalStorage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns initialValue when nothing is in localStorage', () => {
    const { result } = renderHook(() => useLocalStorage('test-key', { foo: 'bar' }))
    expect(result.current[0]).toEqual({ foo: 'bar' })
  })

  it('hydrates existing valid JSON from localStorage', () => {
    localStorage.setItem('test-key', JSON.stringify({ count: 42 }))
    const { result } = renderHook(() => useLocalStorage('test-key', { count: 0 }))
    expect(result.current[0]).toEqual({ count: 42 })
  })

  it('falls back to initialValue if stored value is invalid JSON', () => {
    localStorage.setItem('test-key', 'invalid-json{')
    const { result } = renderHook(() => useLocalStorage('test-key', 'default'))
    expect(result.current[0]).toBe('default')
  })

  it('updates state and localStorage on setValue', () => {
    const { result } = renderHook(() => useLocalStorage('test-key', 'hello'))
    act(() => {
      result.current[1]('world')
    })
    expect(result.current[0]).toBe('world')
    expect(localStorage.getItem('test-key')).toBe(JSON.stringify('world'))
  })

  it('supports functional updates', () => {
    const { result } = renderHook(() => useLocalStorage('test-key', 10))
    act(() => {
      result.current[1]((prev) => prev + 5)
    })
    expect(result.current[0]).toBe(15)
    expect(localStorage.getItem('test-key')).toBe(JSON.stringify(15))
  })
})
