import { useEffect, useState } from 'react'
import { getLaw, getLawCiting, getLawHistory } from '../api'
import type { Chunk, CitingJudgment, LawVersion } from '../api'
import { useToast } from '../context/ToastContext'
import { docTypeLabel, formatDate, formatDateTime, isLegislation, tierName } from '../lib/format'
import { Attribution } from './Attribution'
import { StatusBadge, TierBadge, TreatmentBadge } from './Badges'

type Tab = 'history' | 'citing'

interface Props {
  chunk: Chunk
  /** Navigate the reading pane to another chunk (e.g. a citing judgment). */
  onNavigate: (chunkId: string) => void
}

/**
 * Reading pane for a single provision or judgment paragraph: serif text at a
 * readable measure, hierarchy breadcrumb, metadata, plus History and Citing
 * tabs fed by the /api/law endpoints.
 */
export function ProvisionView({ chunk, onNavigate }: Props) {
  const toast = useToast()
  const [tab, setTab] = useState<Tab>('history')
  const [history, setHistory] = useState<LawVersion[] | null>(null)
  const [citing, setCiting] = useState<CitingJudgment[] | null>(null)
  const [tabLoading, setTabLoading] = useState(false)
  const [tabError, setTabError] = useState<string | null>(null)

  // Reset tab data when the provision changes.
  useEffect(() => {
    setHistory(null)
    setCiting(null)
    setTab('history')
    setTabError(null)
  }, [chunk.chunk_id])

  useEffect(() => {
    const needsLoad =
      (tab === 'history' && history === null) || (tab === 'citing' && citing === null)
    if (!needsLoad) return
    let cancelled = false
    setTabLoading(true)
    setTabError(null)
    const load =
      tab === 'history'
        ? getLawHistory(chunk.citation).then((r) => {
            if (!cancelled) setHistory(r.versions)
          })
        : getLawCiting(chunk.citation).then((r) => {
            if (!cancelled) setCiting(r.citing)
          })
    load
      .catch((e: unknown) => {
        if (!cancelled) setTabError(e instanceof Error ? e.message : 'Failed to load.')
      })
      .finally(() => {
        if (!cancelled) setTabLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [tab, history, citing, chunk.citation])

  const openCiting = async (j: CitingJudgment) => {
    try {
      const res = await getLaw(j.citation)
      const first = res.found ? res.chunks[0] : undefined
      if (first) {
        onNavigate(first.chunk_id)
      } else {
        toast.push(`“${j.citation}” is not in the corpus.`, 'info')
      }
    } catch (e) {
      toast.push(e instanceof Error ? e.message : 'Lookup failed.')
    }
  }

  return (
    <article className="mx-auto max-w-3xl px-5 py-6 sm:px-8">
      {chunk.hierarchy_path.length > 0 && (
        <nav aria-label="Hierarchy" className="mb-2 text-xs text-paper-600">
          {chunk.hierarchy_path.map((seg, i) => (
            <span key={`${i}-${seg}`}>
              {i > 0 && <span className="mx-1 text-paper-400">›</span>}
              {seg}
            </span>
          ))}
        </nav>
      )}

      <h2 className="font-serif text-xl font-semibold text-ink-950">{chunk.citation}</h2>

      <div className="mt-2 mb-4 flex flex-wrap items-center gap-1.5">
        <TierBadge tier={chunk.authority_tier} />
        <StatusBadge status={chunk.status} />
        <TreatmentBadge treatment={chunk.treatment} />
        <span className="meta-chip border-paper-300 bg-paper-50 text-paper-700">
          {docTypeLabel(chunk.doc_type)}
        </span>
        {chunk.court && (
          <span className="meta-chip border-paper-300 bg-paper-50 text-paper-700">
            {chunk.court}
            {chunk.decision_date ? ` · ${formatDate(chunk.decision_date)}` : ''}
          </span>
        )}
        <a
          href={chunk.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[11px] font-medium text-ink-700 transition-colors hover:text-ink-950 hover:underline"
          title={`Authority tier ${chunk.authority_tier}: ${tierName(chunk.authority_tier)}`}
        >
          View on official source
          <svg viewBox="0 0 16 16" className="h-3 w-3 fill-current" aria-hidden="true">
            <path d="M6 3v1.5h4.4L3 11.9 4.1 13l7.4-7.4V10H13V3H6Z" />
          </svg>
        </a>
      </div>

      <div className="rounded-md border border-paper-200 bg-white p-5 font-serif text-[15px] leading-7 whitespace-pre-wrap text-ink-950 shadow-card">
        {chunk.text}
      </div>

      {isLegislation(chunk.doc_type, chunk.collection) && <Attribution className="mt-3" />}

      <div className="mt-6">
        <div
          className="flex gap-4 border-b border-paper-200"
          role="tablist"
          aria-label="Provision detail"
        >
          {(
            [
              { id: 'history', label: 'Version history' },
              { id: 'citing', label: 'Citing judgments' },
            ] as { id: Tab; label: string }[]
          ).map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={`-mb-px border-b-2 px-1 pb-2 text-sm font-medium transition-colors ${
                tab === t.id
                  ? 'border-ink-900 text-ink-950'
                  : 'border-transparent text-paper-600 hover:text-ink-900'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="pt-3 text-sm" role="tabpanel">
          {tabLoading && <p className="text-paper-600">Loading…</p>}
          {tabError && <p className="text-danger-700">{tabError}</p>}

          {!tabLoading && !tabError && tab === 'history' && history && (
            <>
              {history.length === 0 ? (
                <p className="text-paper-600">No version history recorded for this provision.</p>
              ) : (
                <ol className="relative space-y-3 border-l border-paper-200 pl-4">
                  {history.map((v, i) => (
                    <li key={`${v.sso_version_date}-${i}`} className="relative">
                      <span
                        className={`absolute top-1.5 -left-[21.5px] h-2.5 w-2.5 rounded-full border-2 border-paper-25 ${
                          i === 0 ? 'bg-ink-700' : 'bg-paper-300'
                        }`}
                        aria-hidden="true"
                      />
                      <p className="font-medium text-ink-900">
                        Version of {formatDate(v.sso_version_date)}
                        {i === 0 && (
                          <span className="ml-2 rounded-sm bg-ink-50 px-1.5 py-0.5 text-[10px] font-semibold text-ink-800">
                            Latest fetched
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-paper-600">
                        Fetched {formatDateTime(v.fetched_at)} ·{' '}
                        <a
                          href={v.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-ink-700 hover:underline"
                        >
                          source
                        </a>
                      </p>
                    </li>
                  ))}
                </ol>
              )}
            </>
          )}

          {!tabLoading && !tabError && tab === 'citing' && citing && (
            <>
              {citing.length === 0 ? (
                <p className="text-paper-600">No judgments in the corpus cite this provision.</p>
              ) : (
                <ul className="divide-y divide-paper-200">
                  {citing.map((j, i) => (
                    <li key={`${j.citation}-${i}`} className="flex items-center gap-3 py-2">
                      <button
                        type="button"
                        onClick={() => void openCiting(j)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <span className="block truncate font-medium text-ink-900 hover:text-ink-950 hover:underline">
                          {j.citation}
                        </span>
                        <span className="block text-xs text-paper-600">
                          {j.court} · {formatDate(j.decision_date)}
                        </span>
                      </button>
                      <TreatmentBadge treatment={j.treatment} />
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      </div>
    </article>
  )
}
