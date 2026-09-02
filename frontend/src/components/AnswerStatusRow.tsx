import type { ChatMeta, Source } from '../api'
import { formatDate, isProblematic, problemSeverity, statusLabel } from '../lib/format'
import { StatusBadge, TierBadge, WarningBadge } from './Badges'

interface Props {
  sources: Source[]
  meta: ChatMeta | null
}

/**
 * The per-answer status chip row: primary source authority tier, its
 * in-force / decision date, the temporal basis of the answer, and a
 * prominent warning when any cited source is not good law.
 */
export function AnswerStatusRow({ sources, meta }: Props) {
  const authoritySources = sources.filter((s) => s.collection === 'sg_law')

  // Primary source = highest authority (lowest tier), ties broken by citation order.
  let primary: Source | null = null
  for (const s of authoritySources) {
    if (primary === null || s.authority_tier < primary.authority_tier) primary = s
  }

  // Worst offender drives the warning badge.
  let severity: 'red' | 'amber' | null = null
  const problems: string[] = []
  for (const s of authoritySources) {
    if (!isProblematic(s.status, s.treatment)) continue
    const sev = problemSeverity(s.status, s.treatment)
    if (sev === 'red') severity = 'red'
    else if (sev === 'amber' && severity !== 'red') severity = 'amber'
    const why = s.treatment === 'overruled' ? 'overruled' : statusLabel(s.status).toLowerCase()
    problems.push(`${s.citation} (${why})`)
  }

  if (!primary && !meta && severity === null) return null

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {primary && (
        <>
          <TierBadge tier={primary.authority_tier} />
          <StatusBadge status={primary.status} />
          <span className="meta-chip border-paper-300 bg-paper-50 text-paper-700">
            {primary.decision_date
              ? `Decided ${formatDate(primary.decision_date)}`
              : statusLabel(primary.status) === 'In force'
                ? 'Current version'
                : statusLabel(primary.status)}
          </span>
        </>
      )}
      {!primary && sources.length > 0 && (
        <span className="meta-chip border-paper-300 bg-paper-50 text-paper-600">
          No authoritative source cited
        </span>
      )}
      {meta && (
        <span
          className="meta-chip border-paper-300 bg-white text-paper-700"
          title="The law as it stood on this date"
        >
          As at {formatDate(meta.temporal_basis)}
        </span>
      )}
      {severity && (
        <WarningBadge severity={severity}>
          <span title={problems.join('; ')}>
            Cited authority not fully in force: {problems.join('; ')}
          </span>
        </WarningBadge>
      )}
    </div>
  )
}
