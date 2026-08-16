import { useEffect, useRef } from 'react'

export interface RealtimeEvent {
  topic: string
  data: Record<string, unknown>
}

type Listener = (event: RealtimeEvent) => void

/**
 * One shared WebSocket to /ws/events for the whole app. Pages subscribe via
 * useRealtime and get events fanned out to them; switching tabs does not
 * reopen the connection. Reconnects with backoff while at least one page is
 * subscribed, and closes once the last one unmounts.
 */
const listeners = new Set<Listener>()
let socket: WebSocket | null = null
let retry = 0
let retryTimer: ReturnType<typeof setTimeout> | undefined
let closeTimer: ReturnType<typeof setTimeout> | undefined

// How long to wait after the last subscriber leaves before closing the
// socket. React Router unmounts the old page before mounting the next one
// (and StrictMode remounts on first load), so an immediate close would
// churn the connection on every tab switch. A short grace period lets a
// same-tick resubscribe cancel the close instead.
const CLOSE_GRACE_MS = 1000

function getWsUrl(token: string): string {
  const customWsUrl = import.meta.env.VITE_WS_URL
  if (customWsUrl) {
    return `${customWsUrl}/ws/events?token=${encodeURIComponent(token)}`
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/events?token=${encodeURIComponent(token)}`
}

function connect() {
  const token = localStorage.getItem('access_token')
  if (!token) return

  const url = getWsUrl(token)

  socket = new WebSocket(url)
  socket.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data) as RealtimeEvent
      listeners.forEach((listener) => listener(event))
    } catch {
      // ignore malformed frames
    }
  }
  socket.onopen = () => {
    retry = 0
  }
  socket.onclose = () => {
    socket = null
    if (listeners.size === 0) return
    const delay = Math.min(1000 * 2 ** retry, 15000)
    retry += 1
    retryTimer = setTimeout(connect, delay)
  }
}

function subscribe(listener: Listener) {
  listeners.add(listener)
  clearTimeout(closeTimer)
  if (!socket) connect()
  return () => {
    listeners.delete(listener)
    if (listeners.size > 0) return
    closeTimer = setTimeout(() => {
      clearTimeout(retryTimer)
      socket?.close()
      socket = null
    }, CLOSE_GRACE_MS)
  }
}

/**
 * Subscribe the current page to the shared realtime feed. The underlying
 * socket is shared across pages and survives tab switches.
 */
export function useRealtime(onEvent: Listener) {
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => subscribe((event) => handlerRef.current(event)), [])
}
