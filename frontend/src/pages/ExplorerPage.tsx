import { useEffect, useState } from 'react'
import { getChunk, getCorpusDoc, getCorpusToc, search } from '../api'
import type { Chunk, CorpusDoc, SearchResult, TocEntry } from '../api'
import { StatusBadge, TierBadge } from '../components/Badges'
import { DocTree } from '../components/DocTree'
import { ProvisionView } from '../components/ProvisionView'
import { useToast } from '../context/ToastContext'
import { usePageTitle } from '../hooks/usePageTitle'
import { docTypeLabel, formatDate } from '../lib/format'

const DOC_TYPE_TABS = [
  { label: 'All', value: '' },
  { label: 'Acts', value: 'act' },
  { label: 'Subsidiary', value: 'subsidiary_legislation' },
  { label: 'Judgments', value: 'judgment' },
  { label: 'Practice Directions', value: 'practice_direction' },
]

type Mode = 'browse' | 'search'

export function ExplorerPage() {
  usePageTitle('Explorer · SG Law Assistant')
  const toast = useToast()
  const [mode, setMode] = useState<Mode>('browse')

  // Browse state
  const [q, setQ] = useState('')
  const [docType, setDocType] = useState('')
  const [toc, setToc] = useState<TocEntry[]>([])
  const [tocLoading, setTocLoading] = useState(false)
  const [selectedDoc, setSelectedDoc] = useState<CorpusDoc | null>(null)
  const [docLoading, setDocLoading] = useState(false)

  // Full-text search state
  const [ftQuery, setFtQuery] = useState('')
  const [ftResults, setFtResults] = useState<SearchResult[] | null>(null)
  const [ftLowConfidence, setFtLowConfidence] = useState(false)
  const [ftLoading, setFtLoading] = useState(false)

  // Reading pane
  const [chunk, setChunk] = useState<Chunk | null>(null)
  const [chunkLoading, setChunkLoading] = useState(false)

  // Server-side corpus listing, debounced on the q param.
  useEffect(() => {
    let cancelled = false
    setTocLoading(true)
    const timer = window.setTimeout(() => {
      getCorpusToc({ doc_type: docType || undefined, q: q.trim() || undefined })
        .then((entries) => {
          if (!cancelled) setToc(entries)
        })
        .catch((e: unknown) => {
          if (!cancelled) toast.push(e instanceof Error ? e.message : 'Failed to load corpus.')
        })
        .finally(() => {
          if (!cancelled) setTocLoading(false)
        })
    }, 300)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [q, docType, toast])

  const openDoc = (entry: TocEntry) => {
    setDocLoading(true)
    setSelectedDoc(null)
    getCorpusDoc(entry.doc_id)
      .then(setSelectedDoc)
      .catch((e: unknown) =>
        toast.push(e instanceof Error ? e.message : 'Failed to load document.'),
      )
      .finally(() => setDocLoading(false))
  }

  const openChunk = (chunkId: string) => {
    setChunkLoading(true)
    getChunk(chunkId)
      .then(setChunk)
      .catch((e: unknown) =>
        toast.push(e instanceof Error ? e.message : 'Failed to load provision.'),
      )
      .finally(() => setChunkLoading(false))
  }

  const runFullTextSearch = () => {
    const query = ftQuery.trim()
    if (!query || ftLoading) return
    setFtLoading(true)
    search({ query, top_k: 20 })
      .then((res) => {
        setFtResults(res.results)
        setFtLowConfidence(res.low_confidence)
      })
      .catch((e: unknown) => toast.push(e instanceof Error ? e.message : 'Search failed.'))
      .finally(() => setFtLoading(false))
  }

  return (
    <div className="flex h-full min-w-0 flex-1">
      {/* Corpus list / search column */}
      <div className="flex w-80 shrink-0 flex-col border-r border-paper-200 bg-paper-25">
        <div className="border-b border-paper-200 p-3">
          <div className="mb-2 flex rounded-md border border-paper-300 bg-white p-0.5">
            {(
              [
                { id: 'browse', label: 'Browse corpus' },
                { id: 'search', label: 'Full-text search' },
              ] as { id: Mode; label: string }[]
            ).map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setMode(m.id)}
                className={`flex-1 rounded-[5px] px-2 py-1 text-xs font-medium transition-colors ${
                  mode === m.id ? 'bg-ink-900 text-white' : 'text-paper-700 hover:bg-paper-100'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          {mode === 'browse' ? (
            <>
              <input
                type="search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search titles and citations"
                aria-label="Search the corpus list"
                className="input-base w-full"
              />
              <div className="mt-2 flex flex-wrap gap-1">
                {DOC_TYPE_TABS.map((t) => (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => setDocType(t.value)}
                    className={`rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors ${
                      docType === t.value
                        ? 'border-ink-900 bg-ink-900 text-white'
                        : 'border-paper-300 bg-white text-paper-700 hover:bg-paper-100'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <div className="flex gap-1.5">
              <input
                type="search"
                value={ftQuery}
                onChange={(e) => setFtQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') runFullTextSearch()
                }}
                placeholder="Search the full text of the corpus"
                aria-label="Full-text search"
                className="input-base min-w-0 flex-1"
              />
              <button
                type="button"
                onClick={runFullTextSearch}
                disabled={ftLoading || !ftQuery.trim()}
                className="rounded-md bg-ink-900 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-ink-700 disabled:opacity-40"
              >
                {ftLoading ? '…' : 'Go'}
              </button>
            </div>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {mode === 'browse' ? (
            <>
              {tocLoading && <p className="px-2 py-3 text-xs text-paper-500">Loading corpus…</p>}
              {!tocLoading && toc.length === 0 && (
                <p className="px-2 py-3 text-xs text-paper-500">No documents match.</p>
              )}
              <ul className="space-y-0.5">
                {toc.map((entry) => (
                  <li key={entry.doc_id}>
                    <button
                      type="button"
                      onClick={() => openDoc(entry)}
                      className={`w-full rounded-md px-2 py-1.5 text-left transition-colors hover:bg-paper-100 ${
                        selectedDoc?.doc_id === entry.doc_id ? 'bg-ink-50' : ''
                      }`}
                    >
                      <span className="block truncate text-[13px] font-medium text-ink-900">
                        {entry.title}
                      </span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-1">
                        <StatusBadge status={entry.status} />
                        <TierBadge tier={entry.authority_tier} compact />
                        <span className="text-[10px] text-paper-500">
                          {docTypeLabel(entry.doc_type)}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <>
              {ftResults === null && !ftLoading && (
                <p className="px-2 py-3 text-xs text-paper-500">
                  Search runs the same hybrid retrieval pipeline the assistant uses — results are
                  ranked by relevance and authority.
                </p>
              )}
              {ftLoading && <p className="px-2 py-3 text-xs text-paper-500">Searching…</p>}
              {ftResults !== null && !ftLoading && (
                <>
                  {ftLowConfidence && (
                    <p className="mx-1 mb-1.5 rounded-sm border border-caution-300 bg-caution-50 px-2 py-1 text-[11px] text-caution-900">
                      Weak matches only — treat these results with caution.
                    </p>
                  )}
                  {ftResults.length === 0 && (
                    <p className="px-2 py-3 text-xs text-paper-500">No results.</p>
                  )}
                  <ul className="space-y-1">
                    {ftResults.map((r) => (
                      <li key={r.chunk_id}>
                        <button
                          type="button"
                          onClick={() => openChunk(r.chunk_id)}
                          className={`w-full rounded-md border px-2 py-1.5 text-left transition-colors hover:border-ink-300 hover:bg-ink-50 ${
                            chunk?.chunk_id === r.chunk_id
                              ? 'border-ink-300 bg-ink-50'
                              : 'border-paper-200 bg-white'
                          }`}
                        >
                          <span className="block truncate text-[13px] font-medium text-ink-900">
                            {r.citation}
                          </span>
                          <span className="mt-0.5 line-clamp-2 block text-[11px] leading-4 text-paper-600">
                            {r.snippet || r.text}
                          </span>
                          <span className="mt-1 flex items-center gap-1.5 text-[10px] text-paper-500 tabular-nums">
                            <span>final {r.final_score.toFixed(3)}</span>
                            <span>· relevance {r.ce_score.toFixed(3)}</span>
                            <span>· authority {r.authority_score.toFixed(3)}</span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* Document outline column (browse mode) */}
      {mode === 'browse' && (docLoading || selectedDoc) && (
        <div className="flex w-72 shrink-0 flex-col border-r border-paper-200 bg-paper-100/60">
          {docLoading && <p className="px-3 py-4 text-xs text-paper-500">Loading structure…</p>}
          {selectedDoc && (
            <>
              <div className="border-b border-paper-200 px-3 py-2.5">
                <h3 className="text-[13px] leading-5 font-semibold text-ink-950">
                  {selectedDoc.title}
                </h3>
                <div className="mt-1 flex flex-wrap items-center gap-1">
                  <StatusBadge status={selectedDoc.status} />
                  <span className="text-[10px] text-paper-600">
                    SSO version {formatDate(selectedDoc.sso_version_date)}
                  </span>
                </div>
                <a
                  href={selectedDoc.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 inline-block text-[11px] font-medium text-ink-700 hover:underline"
                >
                  View on SSO
                </a>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto p-2">
                <DocTree
                  nodes={selectedDoc.tree}
                  selectedChunkId={chunk?.chunk_id ?? null}
                  onSelect={openChunk}
                />
              </div>
            </>
          )}
        </div>
      )}

      {/* Reading pane */}
      <div className="min-w-0 flex-1 overflow-y-auto bg-paper-50">
        {chunkLoading && <p className="px-8 py-6 text-sm text-paper-600">Loading provision…</p>}
        {!chunkLoading && chunk && <ProvisionView chunk={chunk} onNavigate={openChunk} />}
        {!chunkLoading && !chunk && (
          <div className="flex h-full items-center justify-center">
            <div className="max-w-sm text-center">
              <p className="text-sm font-medium text-paper-700">Source explorer</p>
              <p className="mt-1 text-xs leading-5 text-paper-500">
                Browse the corpus on the left, open a document's structure, and select a provision
                to read its current text, version history, and the judgments that cite it. Or use
                full-text search to jump straight to a provision.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
