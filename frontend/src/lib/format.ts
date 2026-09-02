/** Display helpers shared across the app. */

export const TIER_NAMES: Record<number, string> = {
  1: 'Constitution',
  2: 'Act',
  3: 'Subsidiary legislation',
  4: 'Binding judgment',
  5: 'Lower court',
  6: 'Guidance',
}

export function tierName(tier: number): string {
  return TIER_NAMES[tier] ?? `Tier ${tier}`
}

export function statusLabel(status: string): string {
  switch (status) {
    case 'in_force':
      return 'In force'
    case 'repealed':
      return 'Repealed'
    case 'spent':
      return 'Spent'
    case 'not_yet_commenced':
      return 'Not yet commenced'
    case 'amended':
      return 'Amended'
    default:
      return humanize(status)
  }
}

export function docTypeLabel(docType: string): string {
  switch (docType) {
    case 'act':
      return 'Act'
    case 'subsidiary_legislation':
      return 'Subsidiary legislation'
    case 'judgment':
      return 'Judgment'
    case 'practice_direction':
      return 'Practice direction'
    case 'constitution':
      return 'Constitution'
    case 'user_doc':
      return 'Your document'
    default:
      return humanize(docType)
  }
}

export function humanize(value: string): string {
  if (!value) return value
  const spaced = value.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

const DATE_FMT = new Intl.DateTimeFormat('en-SG', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

const DATETIME_FMT = new Intl.DateTimeFormat('en-SG', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/** Format an ISO date (YYYY-MM-DD or full timestamp) as e.g. "11 Aug 2026". */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return DATE_FMT.format(d)
}

/** Format an ISO timestamp with time, e.g. "11 Aug 2026, 06:12". */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return DATETIME_FMT.format(d)
}

/** True when a source's status/treatment warrants a caution badge. */
export function isProblematic(status: string, treatment: string): boolean {
  return status !== 'in_force' || treatment === 'overruled'
}

/** Severity used for the answer warning badge. */
export function problemSeverity(status: string, treatment: string): 'red' | 'amber' | null {
  if (status === 'repealed' || treatment === 'overruled') return 'red'
  if (status !== 'in_force') return 'amber'
  return null
}

export const FALLBACK_DISCLAIMER =
  'This assistant provides legal information, not legal advice.'

export const FALLBACK_ATTRIBUTION =
  'Legislation is © Singapore Government, reproduced with permission of the Attorney-General’s Chambers. ' +
  'Check SSO for the latest version; SSO downloads are not authoritative (s 48 Interpretation Act 1965 does not apply) — the Gazette is authoritative.'

/** Legislation (as opposed to judgments / user documents) attracts AGC attribution. */
export function isLegislation(docType: string, collection?: string): boolean {
  if (collection === 'user_docs') return false
  return docType !== 'judgment' && docType !== 'user_doc'
}
