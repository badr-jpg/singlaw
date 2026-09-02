import { useCallback, useRef, useState } from 'react'
import type {
  ChatMeta,
  ChatRequest,
  DoneEvent,
  ErrorEvent,
  SourcesEvent,
  TokenEvent,
  ValidationEvent,
} from '../api'

export interface ChatStreamHandlers {
  onMeta: (meta: ChatMeta) => void
  onSources: (sources: SourcesEvent) => void
  onToken: (token: TokenEvent) => void
  onValidation: (validation: ValidationEvent) => void
  onDone: (done: DoneEvent) => void
  onError: (message: string) => void
  /** Called when the user aborts the stream via stop(). */
  onAbort: () => void
}

/**
 * Streams POST /api/chat as Server-Sent Events.
 *
 * EventSource cannot POST, so this reads the fetch body as a stream and
 * parses SSE frames by hand: lines are accumulated until a blank line
 * terminates a frame; `event:` names the event and `data:` lines carry the
 * JSON payload (joined with \n when repeated). Partial lines/frames are
 * buffered across network chunks, and CRLF line endings are tolerated.
 */
export function useChatStream() {
  const abortRef = useRef<AbortController | null>(null)
  const [streaming, setStreaming] = useState(false)

  const stop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const send = useCallback(async (req: ChatRequest, handlers: ChatStreamHandlers) => {
    const controller = new AbortController()
    abortRef.current = controller
    setStreaming(true)

    let eventName = ''
    let dataLines: string[] = []
    let finished = false

    const dispatch = (name: string, data: string) => {
      if (finished) return
      let payload: unknown
      try {
        payload = JSON.parse(data)
      } catch {
        handlers.onError('The server sent a malformed event.')
        return
      }
      switch (name) {
        case 'meta':
          handlers.onMeta(payload as ChatMeta)
          break
        case 'sources':
          handlers.onSources(payload as SourcesEvent)
          break
        case 'token':
          handlers.onToken(payload as TokenEvent)
          break
        case 'validation':
          handlers.onValidation(payload as ValidationEvent)
          break
        case 'done':
          finished = true
          handlers.onDone(payload as DoneEvent)
          break
        case 'error':
          finished = true
          handlers.onError((payload as ErrorEvent).message || 'The server reported an error.')
          break
        default:
          // Unknown event types are ignored (forward compatibility).
          break
      }
    }

    const processLine = (raw: string) => {
      const line = raw.endsWith('\r') ? raw.slice(0, -1) : raw
      if (line === '') {
        // Blank line terminates the frame.
        if (dataLines.length > 0) dispatch(eventName || 'message', dataLines.join('\n'))
        eventName = ''
        dataLines = []
        return
      }
      if (line.startsWith(':')) return // SSE comment / keep-alive
      if (line.startsWith('event:')) {
        eventName = line.slice('event:'.length).trim()
      } else if (line.startsWith('data:')) {
        let value = line.slice('data:'.length)
        if (value.startsWith(' ')) value = value.slice(1)
        dataLines.push(value)
      }
    }

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(req),
        signal: controller.signal,
      })
      if (!res.ok) {
        let detail = ''
        try {
          const body: unknown = await res.json()
          if (body && typeof body === 'object') {
            const d = (body as Record<string, unknown>)['detail']
            if (typeof d === 'string') detail = d
          }
        } catch {
          // ignore non-JSON error body
        }
        handlers.onError(detail || `Chat request failed (${res.status} ${res.statusText})`)
        return
      }
      if (!res.body) {
        handlers.onError('The server returned no response stream.')
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let nl = buffer.indexOf('\n')
        while (nl !== -1) {
          processLine(buffer.slice(0, nl))
          buffer = buffer.slice(nl + 1)
          nl = buffer.indexOf('\n')
        }
      }
      // Flush any trailing data (stream ended without a final blank line).
      buffer += decoder.decode()
      if (buffer.length > 0) processLine(buffer)
      if (dataLines.length > 0) dispatch(eventName || 'message', dataLines.join('\n'))
      if (!finished) {
        handlers.onError('The stream ended unexpectedly before completion.')
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        handlers.onAbort()
      } else if (!finished) {
        handlers.onError(err instanceof Error ? err.message : 'Streaming failed.')
      }
    } finally {
      setStreaming(false)
      if (abortRef.current === controller) abortRef.current = null
    }
  }, [])

  return { streaming, send, stop }
}
