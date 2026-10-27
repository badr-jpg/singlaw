import type { ReactNode } from "react";
import { TriangleAlert } from "lucide-react";
import { humanize, statusLabel, tierName, type Severity } from "@/lib/singlaw";

type Tone = "neutral" | "strong" | "positive" | "caution" | "danger" | "scope";

export function MetaChip({
  tone = "neutral",
  title,
  children,
}: {
  tone?: Tone;
  title?: string | undefined;
  children: ReactNode;
}) {
  return (
    <span className="meta-chip" data-tone={tone} title={title}>
      {children}
    </span>
  );
}

/** Authority tier, e.g. "Act" (tier 2). Lower tier = higher authority. */
export function TierBadge({ tier, compact = true }: { tier: number; compact?: boolean }) {
  return (
    <MetaChip
      tone={tier <= 2 ? "strong" : "neutral"}
      title={`Authority tier ${tier}: ${tierName(tier)}`}
    >
      {compact ? tierName(tier) : `Tier ${tier} · ${tierName(tier)}`}
    </MetaChip>
  );
}

/** Legislation status; repealed renders red, anything else not in force amber. */
export function StatusBadge({ status }: { status: string }) {
  const tone: Tone =
    status === "in_force" ? "positive" : status === "repealed" ? "danger" : "caution";
  return <MetaChip tone={tone}>{statusLabel(status)}</MetaChip>;
}

/** Judicial treatment (overruled red, distinguished amber, followed green). */
export function TreatmentBadge({ treatment }: { treatment: string }) {
  // "unknown" is the backend default (and meaningless for legislation): show nothing
  if (!treatment || treatment === "none" || treatment === "unknown") return null;
  const tone: Tone =
    treatment === "overruled"
      ? "danger"
      : treatment === "distinguished" || treatment === "doubted" || treatment === "not_followed"
        ? "caution"
        : treatment === "good" || treatment === "followed" || treatment === "affirmed" || treatment === "applied"
          ? "positive"
          : "neutral";
  return <MetaChip tone={tone}>{humanize(treatment)}</MetaChip>;
}

/** Prominent warning pill for answers citing repealed / overruled authority. */
export function WarningBadge({ severity, children }: { severity: Severity; children: ReactNode }) {
  return (
    <span className="warning-badge" data-severity={severity}>
      <TriangleAlert aria-hidden="true" />
      {children}
    </span>
  );
}
