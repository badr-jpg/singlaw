import { useState } from 'react'
import { search } from '../api'
import type { SearchResponse } from '../api'
import { useApp } from '../context/AppContext'

interface Props {
  /** The user question that produced this answer. */
  query: string
  docIds: string[] | null
}

/**
 * Collapsible "Show retrieval details" section under each assistant answer.
 * Closed by default; on first open it re-runs the retrieval pipeline with
 * include_debug so a sceptical reader can verify what the system actually
 * retrieved, filtered, and reranked.
 */
export function RetrievalInspector({ query, docIds }: Props) {
  const { openSource } = useApp()
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<SearchResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hydeOpen, setHydeOpen] = useState(false)

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next && data === null && !loading) {
      setLoading(true)
      setError(null)
      search({ query, include_debug: true, doc_ids: docIds })
        .then(setData)
        .catch((e: unknown) =>
          setError(e instanceof Error ? e.message : 'Failed to load retrieval details.'),
        )
        .finally(() => setLoading(false))
    }
  }

  const filteredParts: string[] = []
  if (data) {
    if (data.filtered.repealed > 0)
      filteredParts.push(`${data.filtered.repealed} repealed provisions excluded`)
    if (data.filtered.spent > 0)
      filteredParts.push(`${data.filtered.spent} spent provisions excluded`)
    if (data.filtered.not_yet_commenced > 0)
      filteredParts.push(`${data.filtered.not_yet_commenced} not-yet-commenced provisions excluded`)
  }

  return (
    <div className="text-xs">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="inline-flex items-center gap-1 font-medium text-paper-600 transition-colors hover:text-ink-900"
      >
        <svg
          viewBox="0 0 16 16"
          className={`h-3 w-3 fill-current transition-transform ${open ? 'rotate-90' : ''}`}
          aria-hidden="true"
        >
          <path d="M6 3.5 11 8l-5 4.5v-9Z" />
        </svg>
        {open ? 'Hide retrieval details' : 'Show retrieval details'}
      </button>

      {open && (
        <div className="mt-2 space-y-3 rounded-md border border-paper-200 bg-paper-100 p-3">
          {loading && <p className="text-paper-600">Running retrieval with debug enabled…</p>}
          {error && <p className="text-danger-700">{error}</p>}

          {data && (
            <>
              {data.debug ? (
                <>
                  <section>
                    <h4 className="mb-1 font-semibold text-ink-800">Query rewrites</h4>
                    {data.debug.rewrites.length > 0 ? (
                      <ul className="list-disc space-y-0.5 pl-4 text-paper-700">
                        {data.debug.rewrites.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-paper-500">No rewrites generated.</p>
                    )}
                  </section>

                  <section>
                    <h4 className="mb-1 font-semibold text-ink-800">HyDE document</h4>
                    {data.debug.hyde ? (
                      <>
                        <button
                          type="button"
                          onClick={() => setHydeOpen((v) => !v)}
                          className="font-medium text-ink-700 hover:underline"
                        >
                          {hydeOpen ? 'Collapse' : 'Expand hypothetical document'}
                        </button>
                        {hydeOpen && (
                          <p className="mt-1 rounded-sm border border-paper-200 bg-white p-2 whitespace-pre-wrap text-paper-700">
                            {data.debug.hyde}
                          </p>
                        )}
                      </>
                    ) : (
                      <p className="text-paper-500">Not used for this query.</p>
                    )}
                  </section>

                  {data.debug.citation_shortcircuit.length > 0 && (
                    <section>
                      <h4 className="mb-1 font-semibold text-ink-800">Citation short-circuits</h4>
                      <ul className="list-disc space-y-0.5 pl-4 text-paper-700">
                        {data.debug.citation_shortcircuit.map((c, i) => (
                          <li key={i}>{c}</li>
                        ))}
                      </ul>
                    </section>
                  )}

                  <section>
                    <h4 className="mb-1 font-semibold text-ink-800">Filtering</h4>
                    <p className="text-paper-700">
                      {data.debug.candidates_pre_filter} candidates before status filters.
                      {filteredParts.length > 0
                        ? ` ${filteredParts.join('; ')}.`
                        : ' Nothing excluded.'}
                    </p>
                  </section>

                  <section>
                    <h4 className="mb-1 font-semibold text-ink-800">
                      Candidates before rerank (RRF)
                    </h4>
                    <div className="overflow-x-auto">
                      <table className="w-full border-collapse text-left">
                        <thead>
                          <tr className="border-b border-paper-300 text-paper-600">
                            <th className="py-1 pr-2 font-medium">Citation</th>
                            <th className="py-1 font-medium">RRF score</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.debug.candidates_pre_rerank.map((c) => (
                            <tr key={c.chunk_id} className="border-b border-paper-200 text-ink-800">
                              <td className="py-1 pr-2">
                                <button
                                  type="button"
                                  onClick={() => openSource(c.chunk_id)}
                                  className="text-left hover:text-ink-950 hover:underline"
                                >
                                  {c.citation}
                                </button>
                              </td>
                              <td className="py-1 tabular-nums">{c.rrf_score.toFixed(4)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                </>
              ) : (
                <p className="text-paper-500">The backend returned no debug information.</p>
              )}

              <section>
                <h4 className="mb-1 font-semibold text-ink-800">
                  Final results (after cross-encoder + authority blend)
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-left">
                    <thead>
                      <tr className="border-b border-paper-300 text-paper-600">
                        <th className="py-1 pr-2 font-medium">Citation</th>
                        <th className="py-1 pr-2 font-medium">CE</th>
                        <th className="py-1 pr-2 font-medium">Authority</th>
                        <th className="py-1 font-medium">Final</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.results.map((r) => (
                        <tr key={r.chunk_id} className="border-b border-paper-200 text-ink-800">
                          <td className="py-1 pr-2">
                            <button
                              type="button"
                              onClick={() => openSource(r.chunk_id)}
                              className="text-left hover:text-ink-950 hover:underline"
                            >
                              {r.citation}
                            </button>
                          </td>
                          <td className="py-1 pr-2 tabular-nums">{r.ce_score.toFixed(3)}</td>
                          <td className="py-1 pr-2 tabular-nums">{r.authority_score.toFixed(3)}</td>
                          <td className="py-1 tabular-nums">{r.final_score.toFixed(3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              {data.debug && Object.keys(data.debug.timings_ms).length > 0 && (
                <p className="text-paper-500">
                  Timings:{' '}
                  {Object.entries(data.debug.timings_ms)
                    .map(([k, v]) => `${k} ${Math.round(v)}ms`)
                    .join(' · ')}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
