import { useEffect, useState } from 'react'
import { getChunk } from '../api'
import type { Chunk } from '../api'
import { useApp } from '../context/AppContext'
import { docTypeLabel, formatDate, isLegislation, tierName } from '../lib/format'
import { StatusBadge, TierBadge, TreatmentBadge } from './Badges'
import { Attribution } from './Attribution'

/**
 * Right-hand slide-over showing the full text and metadata of a cited chunk.
 * Opened by clicking a citation chip anywhere in the app. Below the sm
 * breakpoint it covers the full screen.
 */
export function SourcePanel() {
  const { openChunkId, closeSource } = useApp()
  const [chunk, setChunk] = useState<Chunk | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!openChunkId) {
      setChunk(null)
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    getChunk(openChunkId)
      .then((c) => {
        if (!cancelled) setChunk(c)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load source.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [openChunkId])

  useEffect(() => {
    if (!openChunkId) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeSource()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [openChunkId, closeSource])

  if (!openChunkId) return null

  return (
    <>
      {/* Scrim */}
      <div
        className="fixed inset-0 z-30 bg-ink-950/40"
        onClick={closeSource}
        aria-hidden="true"
      />
      <aside
        role="dialog"
        aria-label="Source detail"
        className="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l border-paper-300 bg-paper-25 shadow-panel sm:max-w-xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-paper-200 px-5 py-4">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold tracking-wide text-paper-600 uppercase">
              Cited source
            </p>
            <h2 className="mt-0.5 truncate font-serif text-base font-semibold text-ink-950">
              {chunk?.citation ?? 'Loading…'}
            </h2>
          </div>
          <button
            type="button"
            onClick={closeSource}
            className="rounded-sm p-1 text-paper-600 transition-colors hover:bg-paper-100 hover:text-ink-900"
            aria-label="Close source panel"
          >
            <svg viewBox="0 0 16 16" className="h-4 w-4 fill-current" aria-hidden="true">
              <path d="m4.1 3 3.9 3.9L11.9 3 13 4.1 9.1 8l3.9 3.9-1.1 1.1L8 9.1 4.1 13 3 11.9 6.9 8 3 4.1 4.1 3Z" />
            </svg>
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {loading && <p className="text-sm text-paper-600">Loading source…</p>}
          {error && (
            <p className="rounded-md border border-danger-300 bg-danger-50 px-3 py-2 text-sm text-danger-800">
              {error}
            </p>
          )}
          {chunk && !loading && (
            <>
              {chunk.hierarchy_path.length > 0 && (
                <nav aria-label="Hierarchy" className="mb-3 text-xs text-paper-600">
                  {chunk.hierarchy_path.map((seg, i) => (
                    <span key={`${i}-${seg}`}>
                      {i > 0 && <span className="mx-1 text-paper-400">›</span>}
                      {seg}
                    </span>
                  ))}
                </nav>
              )}

              <div className="mb-4 flex flex-wrap items-center gap-1.5">
                <TierBadge tier={chunk.authority_tier} />
                <StatusBadge status={chunk.status} />
                <TreatmentBadge treatment={chunk.treatment} />
                {chunk.collection === 'user_docs' && (
                  <span className="meta-chip border-scope-300 bg-scope-50 text-scope-800">
                    Your document — not legal authority
                  </span>
                )}
              </div>

              <dl className="mb-4 grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-md border border-paper-200 bg-paper-100 px-3 py-2.5 text-xs">
                <dt className="text-paper-600">Type</dt>
                <dd className="text-ink-900">{docTypeLabel(chunk.doc_type)}</dd>
                <dt className="text-paper-600">Authority</dt>
                <dd className="text-ink-900">
                  Tier {chunk.authority_tier} — {tierName(chunk.authority_tier)}
                </dd>
                {chunk.court && (
                  <>
                    <dt className="text-paper-600">Court</dt>
                    <dd className="text-ink-900">{chunk.court}</dd>
                  </>
                )}
                {chunk.decision_date && (
                  <>
                    <dt className="text-paper-600">Decision date</dt>
                    <dd className="text-ink-900">{formatDate(chunk.decision_date)}</dd>
                  </>
                )}
              </dl>

              <div className="font-serif text-[15px] leading-7 whitespace-pre-wrap text-ink-950">
                {chunk.text}
              </div>

              {isLegislation(chunk.doc_type, chunk.collection) && (
                <Attribution className="mt-5 border-t border-paper-200 pt-3" />
              )}
            </>
          )}
        </div>

        {chunk && (
          <footer className="border-t border-paper-200 bg-paper-100 px-5 py-3">
            <a
              href={chunk.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-700 transition-colors hover:text-ink-950 hover:underline"
            >
              View on official source
              <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 fill-current" aria-hidden="true">
                <path d="M6 3v1.5h4.4L3 11.9 4.1 13l7.4-7.4V10H13V3H6Z" />
              </svg>
            </a>
          </footer>
        )}
      </aside>
    </>
  )
}
