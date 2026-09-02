import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getConversation, listDocuments } from '../api'
import { ChatMessageView } from '../components/ChatMessageView'
import type { UiMessage } from '../components/ChatMessageView'
import { Composer } from '../components/Composer'
import type { DocScopeEntry } from '../components/Composer'
import { EmptyState } from '../components/EmptyState'
import { useApp } from '../context/AppContext'
import { useToast } from '../context/ToastContext'
import { useChatStream } from '../hooks/useChatStream'
import { usePageTitle } from '../hooks/usePageTitle'

let localIdCounter = 0
const nextLocalId = (prefix: string) => `${prefix}-${++localIdCounter}`

/** How close to the bottom (px) still counts as "pinned to bottom". */
const PIN_THRESHOLD = 80

export function ChatPage() {
  usePageTitle('Chat · SG Law Assistant')
  const [searchParams, setSearchParams] = useSearchParams()
  const conversationId = searchParams.get('c')
  const { absorbMeta, bumpConversations } = useApp()
  const toast = useToast()
  const { streaming, send, stop } = useChatStream()

  const [messages, setMessages] = useState<UiMessage[]>([])
  const [loadingConversation, setLoadingConversation] = useState(false)
  const [docScope, setDocScope] = useState<DocScopeEntry[]>([])
  const [pinned, setPinned] = useState(true)

  /** The conversation whose messages are currently in state (streamed or fetched). */
  const loadedConvRef = useRef<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const pinnedRef = useRef(true)

  const patchMessage = useCallback((id: string, patch: (m: UiMessage) => UiMessage) => {
    setMessages((ms) => ms.map((m) => (m.id === id ? patch(m) : m)))
  }, [])

  // Adopt document scope passed via /chat?doc=... (from the Documents page),
  // then strip the params so the chip row in the composer is the single scope truth.
  useEffect(() => {
    const docIds = searchParams.getAll('doc')
    if (docIds.length === 0) return
    const next = new URLSearchParams(searchParams)
    next.delete('doc')
    setSearchParams(next, { replace: true })
    listDocuments()
      .then((docs) => {
        setDocScope((current) => {
          const merged = [...current]
          for (const id of docIds) {
            if (merged.some((d) => d.id === id)) continue
            const doc = docs.find((d) => d.id === id)
            merged.push({ id, filename: doc?.filename ?? id })
          }
          return merged
        })
      })
      .catch(() => {
        // Names unavailable — still scope by id so the request is honoured.
        setDocScope((current) => {
          const merged = [...current]
          for (const id of docIds) {
            if (!merged.some((d) => d.id === id)) merged.push({ id, filename: id })
          }
          return merged
        })
      })
  }, [searchParams, setSearchParams])

  // Load conversation history when the ?c= param points somewhere new.
  useEffect(() => {
    if (conversationId === loadedConvRef.current) return
    stop() // switching away from a streaming conversation aborts the stream
    loadedConvRef.current = conversationId
    if (!conversationId) {
      setMessages([])
      return
    }
    let cancelled = false
    setLoadingConversation(true)
    getConversation(conversationId)
      .then((detail) => {
        if (cancelled) return
        const ui: UiMessage[] = []
        let lastUserText: string | null = null
        for (const m of detail.messages) {
          if (m.role === 'user') lastUserText = m.content
          ui.push({
            id: m.id,
            role: m.role,
            content: m.content,
            createdAt: m.created_at ?? null,
            sources: m.sources ?? [],
            meta: m.meta ?? null,
            validation: null,
            streaming: false,
            error: null,
            aborted: false,
            queryText: m.role === 'assistant' ? lastUserText : null,
            docIds: null,
          })
        }
        setMessages(ui)
        const lastMeta = [...detail.messages].reverse().find((m) => m.meta)?.meta
        if (lastMeta) absorbMeta(lastMeta)
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          toast.push(e instanceof Error ? e.message : 'Failed to load conversation.')
          setMessages([])
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingConversation(false)
      })
    return () => {
      cancelled = true
    }
  }, [conversationId, absorbMeta, stop, toast])

  // Stick-to-bottom: keep the newest message in view while streaming, but
  // stop the moment the user scrolls up; the pill below jumps back down.
  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < PIN_THRESHOLD
    pinnedRef.current = atBottom
    setPinned(atBottom)
  }, [])

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior })
    pinnedRef.current = true
    setPinned(true)
  }, [])

  useEffect(() => {
    if (pinnedRef.current) {
      const el = scrollRef.current
      if (el) el.scrollTop = el.scrollHeight
    }
  }, [messages])

  const handleSend = useCallback(
    (text: string) => {
      if (streaming) return
      const docIds = docScope.length > 0 ? docScope.map((d) => d.id) : null
      const now = new Date().toISOString()
      const userMsg: UiMessage = {
        id: nextLocalId('u'),
        role: 'user',
        content: text,
        createdAt: now,
        sources: [],
        meta: null,
        validation: null,
        streaming: false,
        error: null,
        aborted: false,
        queryText: null,
        docIds: null,
      }
      const assistantId = nextLocalId('a')
      const assistantMsg: UiMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        createdAt: now,
        sources: [],
        meta: null,
        validation: null,
        streaming: true,
        error: null,
        aborted: false,
        queryText: text,
        docIds,
      }
      setMessages((ms) => [...ms, userMsg, assistantMsg])
      // A fresh question always re-pins the view to the bottom.
      pinnedRef.current = true
      setPinned(true)

      void send(
        { message: text, conversation_id: conversationId, doc_ids: docIds },
        {
          onMeta: (meta) => {
            absorbMeta(meta)
            patchMessage(assistantId, (m) => ({ ...m, meta }))
            if (!conversationId && meta.conversation_id) {
              // First exchange of a fresh conversation: adopt the backend id
              // without triggering a history refetch over live messages.
              loadedConvRef.current = meta.conversation_id
              setSearchParams({ c: meta.conversation_id }, { replace: true })
            }
          },
          onSources: ({ sources }) => {
            patchMessage(assistantId, (m) => ({ ...m, sources }))
          },
          onToken: ({ text: t }) => {
            patchMessage(assistantId, (m) => ({ ...m, content: m.content + t }))
          },
          onValidation: (validation) => {
            patchMessage(assistantId, (m) => ({ ...m, validation }))
          },
          onDone: () => {
            patchMessage(assistantId, (m) => ({ ...m, streaming: false }))
            // Backend may have auto-titled the conversation after the first
            // exchange — refresh the sidebar list.
            bumpConversations()
          },
          onError: (message) => {
            patchMessage(assistantId, (m) => ({ ...m, streaming: false, error: message }))
            bumpConversations()
          },
          onAbort: () => {
            patchMessage(assistantId, (m) => ({ ...m, streaming: false, aborted: true }))
            bumpConversations()
          },
        },
      )
    },
    [
      streaming,
      docScope,
      conversationId,
      send,
      absorbMeta,
      patchMessage,
      setSearchParams,
      bumpConversations,
    ],
  )

  const showEmpty = messages.length === 0 && !loadingConversation

  return (
    <div className="relative flex h-full min-w-0 flex-1 flex-col bg-paper-25">
      <div ref={scrollRef} onScroll={handleScroll} className="min-h-0 flex-1 overflow-y-auto">
        {loadingConversation && (
          <p className="px-6 py-8 text-sm text-paper-600">Loading conversation…</p>
        )}
        {showEmpty && <EmptyState onAsk={handleSend} />}
        {!showEmpty && !loadingConversation && (
          <div className="mx-auto max-w-3xl space-y-7 px-4 py-6 sm:px-6">
            {messages.map((m) => (
              <ChatMessageView key={m.id} message={m} />
            ))}
          </div>
        )}
      </div>

      {!pinned && !showEmpty && (
        <button
          type="button"
          onClick={() => scrollToBottom('smooth')}
          className="absolute right-1/2 bottom-32 z-10 inline-flex translate-x-1/2 items-center gap-1.5 rounded-full border border-paper-300 bg-white px-3.5 py-1.5 text-xs font-semibold text-ink-800 shadow-pop transition-colors hover:bg-ink-50"
        >
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 fill-current" aria-hidden="true">
            <path d="M8 12.5 2.5 7l1.1-1.1L7 9.3V2h2v7.3l3.4-3.4L13.5 7 8 12.5Z" />
          </svg>
          Jump to latest
        </button>
      )}

      <Composer
        streaming={streaming}
        onSend={handleSend}
        onStop={stop}
        docScope={docScope}
        onAddDoc={(d) => setDocScope((s) => (s.some((x) => x.id === d.id) ? s : [...s, d]))}
        onRemoveDoc={(id) => setDocScope((s) => s.filter((d) => d.id !== id))}
      />
    </div>
  )
}
