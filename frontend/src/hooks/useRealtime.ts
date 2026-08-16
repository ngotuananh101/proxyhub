import { useEffect, useRef } from 'react'

export interface RealtimeEvent {
  topic: string
  data: Record<string, unknown>
}

/**
 * Subscribe to the backend realtime feed (/ws/events), authenticated with
 * the stored JWT. Reconnects with backoff; cleans up on unmount.
 */
export function useRealtime(onEvent: (event: RealtimeEvent) => void) {
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) return

    const base = (import.meta.env.VITE_WS_URL || 'ws://localhost:8000') as string
    const url = `${base}/ws/events?token=${encodeURIComponent(token)}`

    let ws: WebSocket | null = null
    let closed = false
    let retry = 0
    let timer: ReturnType<typeof setTimeout> | undefined

    const connect = () => {
      ws = new WebSocket(url)
      ws.onmessage = (e) => {
        try {
          handlerRef.current(JSON.parse(e.data))
        } catch {
          // ignore malformed frames
        }
      }
      ws.onclose = () => {
        if (closed) return
        const delay = Math.min(1000 * 2 ** retry, 15000)
        retry += 1
        timer = setTimeout(connect, delay)
      }
      ws.onopen = () => {
        retry = 0
      }
    }

    connect()
    return () => {
      closed = true
      if (timer) clearTimeout(timer)
      ws?.close()
    }
  }, [])
}
