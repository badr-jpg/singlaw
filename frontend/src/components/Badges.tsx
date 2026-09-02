import { statusLabel, tierName, humanize } from '../lib/format'

/** Authority tier badge, e.g. "Tier 2 · Act". Lower tier = higher authority. */
export function TierBadge({ tier, compact = false }: { tier: number; compact?: boolean }) {
  const strong = tier <= 2
  return (
    <span
      className={`meta-chip ${
        strong
          ? 'border-ink-200 bg-ink-50 text-ink-800'
          : 'border-paper-300 bg-paper-50 text-paper-700'
      }`}
      title={`Authority tier ${tier}: ${tierName(tier)}`}
    >
      {compact ? tierName(tier) : `Tier ${tier} · ${tierName(tier)}`}
    </span>
  )
}

/** Legislation status badge; repealed renders red, anything not in force amber. */
export function StatusBadge({ status }: { status: string }) {
  const cls =
    status === 'in_force'
      ? 'border-positive-300 bg-positive-50 text-positive-800'
      : status === 'repealed'
        ? 'border-danger-300 bg-danger-50 text-danger-800'
        : 'border-caution-300 bg-caution-50 text-caution-900'
  return <span className={`meta-chip ${cls}`}>{statusLabel(status)}</span>
}

/** Judicial treatment badge (overruled red, distinguished amber, followed green). */
export function TreatmentBadge({ treatment }: { treatment: string }) {
  if (!treatment || treatment === 'none') return null
  const cls =
    treatment === 'overruled'
      ? 'border-danger-300 bg-danger-50 text-danger-800'
      : treatment === 'distinguished' || treatment === 'doubted' || treatment === 'not_followed'
        ? 'border-caution-300 bg-caution-50 text-caution-900'
        : treatment === 'followed' || treatment === 'affirmed' || treatment === 'applied'
          ? 'border-positive-300 bg-positive-50 text-positive-800'
          : 'border-paper-300 bg-paper-50 text-paper-700'
  return <span className={`meta-chip ${cls}`}>{humanize(treatment)}</span>
}

/** Prominent warning pill used on answers citing repealed / overruled authority. */
export function WarningBadge({
  severity,
  children,
}: {
  severity: 'red' | 'amber'
  children: React.ReactNode
}) {
  const cls =
    severity === 'red'
      ? 'border-danger-400 bg-danger-100 text-danger-900'
      : 'border-caution-400 bg-caution-100 text-caution-900'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-xs font-semibold ${cls}`}
    >
      <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0 fill-current" aria-hidden="true">
        <path d="M8 1.5 15.2 14H.8L8 1.5Zm-.75 4.5v4h1.5V6h-1.5Zm0 5v1.5h1.5V11h-1.5Z" />
      </svg>
      {children}
    </span>
  )
}
