import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { ChatMeta } from '../api'
import { FALLBACK_ATTRIBUTION, FALLBACK_DISCLAIMER } from '../lib/format'

interface AppState {
  /** Disclaimer text for the persistent bar (backend-provided when available). */
  disclaimer: string
  /** AGC attribution notice (backend-provided when available). */
  attribution: string
  /** Record trust text from a chat meta event. */
  absorbMeta: (meta: ChatMeta) => void

  /** Chunk currently shown in the right-hand source slide-over, if any. */
  openChunkId: string | null
  openSource: (chunkId: string) => void
  closeSource: () => void

  /** Bumped after each completed answer so the sidebar refetches conversations. */
  conversationsVersion: number
  bumpConversations: () => void
}

const AppCtx = createContext<AppState | null>(null)

export function useApp(): AppState {
  const ctx = useContext(AppCtx)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [disclaimer, setDisclaimer] = useState(FALLBACK_DISCLAIMER)
  const [attribution, setAttribution] = useState(FALLBACK_ATTRIBUTION)
  const [openChunkId, setOpenChunkId] = useState<string | null>(null)
  const [conversationsVersion, setConversationsVersion] = useState(0)

  const absorbMeta = useCallback((meta: ChatMeta) => {
    if (meta.disclaimer) setDisclaimer(meta.disclaimer)
    if (meta.attribution) setAttribution(meta.attribution)
  }, [])

  const openSource = useCallback((chunkId: string) => setOpenChunkId(chunkId), [])
  const closeSource = useCallback(() => setOpenChunkId(null), [])
  const bumpConversations = useCallback(() => setConversationsVersion((v) => v + 1), [])

  const value = useMemo(
    () => ({
      disclaimer,
      attribution,
      absorbMeta,
      openChunkId,
      openSource,
      closeSource,
      conversationsVersion,
      bumpConversations,
    }),
    [
      disclaimer,
      attribution,
      absorbMeta,
      openChunkId,
      openSource,
      closeSource,
      conversationsVersion,
      bumpConversations,
    ],
  )

  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>
}
