import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import {
  docTypeLabel,
  statusLabel,
  statusTone,
  tierLabel,
  tierName,
  treatmentLabel,
  treatmentTone,
  type Tone,
} from "./helpers";

export function ExplorerBadge({
  tone = "muted",
  children,
  title,
  plain = false,
}: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
  plain?: boolean;
}) {
  return (
    <span className={`xp-badge ${tone}${plain ? " plain" : ""}`} title={title}>
      {children}
    </span>
  );
}

/** Legislation status; repealed is red and carries a warning glyph. */
export function StatusBadge({ status }: { status: string | null | undefined }) {
  const label = statusLabel(status);
  if (!label) return null;
  const tone = statusTone(status);
  return (
    <ExplorerBadge tone={tone} title={`Status: ${label}`}>
      {tone === "danger" && <AlertTriangle aria-hidden="true" />}
      {label}
    </ExplorerBadge>
  );
}

/** Authority tier: 1 Constitution … 6 Guidance. */
export function TierBadge({
  tier,
  long = false,
}: {
  tier: number | null | undefined;
  long?: boolean;
}) {
  return (
    <ExplorerBadge tone="brand" title={tierLabel(tier)}>
      {long ? tierLabel(tier) : tierName(tier)}
    </ExplorerBadge>
  );
}

/** Judicial treatment; overruled is red, distinguished amber, unknown hidden. */
export function TreatmentBadge({ treatment }: { treatment: string | null | undefined }) {
  const label = treatmentLabel(treatment);
  if (!label) return null;
  const tone = treatmentTone(treatment);
  return (
    <ExplorerBadge tone={tone} title={`Treatment: ${label}`}>
      {tone === "danger" && <AlertTriangle aria-hidden="true" />}
      {label}
    </ExplorerBadge>
  );
}

export function DocTypeBadge({ docType }: { docType: string | null | undefined }) {
  return <ExplorerBadge>{docTypeLabel(docType)}</ExplorerBadge>;
}
