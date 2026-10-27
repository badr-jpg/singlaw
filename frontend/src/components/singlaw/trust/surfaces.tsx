import type { ReactNode } from "react";
import { ExternalLink, LifeBuoy, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { ChatMeta, Source, ValidationEvent } from "@/lib/api";
import {
  FALLBACK_ATTRIBUTION,
  answerWarning,
  filteredSummary,
  formatDate,
  lowConfidenceExplanation,
  primarySource,
  statusLabel,
} from "@/lib/singlaw";
import { MetaChip, StatusBadge, TierBadge, WarningBadge } from "./badges";

/**
 * Per-answer status row: primary source tier and status, the temporal basis of
 * the answer, and a warning when any cited authority is not good law.
 */
export function AnswerStatusRow({
  sources,
  meta,
  validation,
}: {
  sources: Source[];
  meta: ChatMeta | undefined;
  validation?: ValidationEvent | undefined;
}) {
  const primary = primarySource(sources);
  const warning = answerWarning(sources);
  if (!primary && !meta && !warning && !validation) return null;
  return (
    <div className="trust-row" aria-label="Answer status">
      {primary && (
        <>
          <TierBadge tier={primary.authority_tier} />
          <StatusBadge status={primary.status} />
          <MetaChip>
            {primary.decision_date
              ? `Decided ${formatDate(primary.decision_date)}`
              : primary.status === "in_force"
                ? "Current version"
                : statusLabel(primary.status)}
          </MetaChip>
        </>
      )}
      {!primary && sources.length > 0 && <MetaChip>No authoritative source cited</MetaChip>}
      {meta?.temporal_basis && (
        <MetaChip title="The law as it stood on this date">
          As at {formatDate(meta.temporal_basis)}
        </MetaChip>
      )}
      {warning && (
        <WarningBadge severity={warning.severity}>
          <span title={warning.problems.join("; ")}>
            Cited authority not fully in force: {warning.problems.join("; ")}
          </span>
        </WarningBadge>
      )}
      <ValidationIndicator validation={validation} />
    </div>
  );
}

/** Wraps an answer the backend flagged as low confidence. */
export function LowConfidenceFrame({
  reasons,
  children,
}: {
  reasons: string[] | undefined;
  children: ReactNode;
}) {
  return (
    <div className="low-confidence" role="group" aria-label="Low-confidence answer">
      <p className="low-confidence-note">
        <TriangleAlert aria-hidden="true" />
        <span>{lowConfidenceExplanation(reasons)}</span>
      </p>
      {children}
    </div>
  );
}

/** Referral card shown before an answer when the question is high-stakes. */
export function HighStakesCard({ highStakes }: { highStakes: ChatMeta["high_stakes"] }) {
  if (!highStakes.triggered) return null;
  return (
    <aside className="high-stakes" aria-label="Speak to a professional">
      <div className="high-stakes-head">
        <LifeBuoy aria-hidden="true" />
        <div>
          <strong>This looks like a situation to take to a professional.</strong>
          {highStakes.reasons.length > 0 && <p>{highStakes.reasons.join(" · ")}</p>}
        </div>
      </div>
      {highStakes.referrals.length > 0 && (
        <ul className="high-stakes-list">
          {highStakes.referrals.map((r) => (
            <li key={`${r.name}-${r.url}`}>
              <a href={r.url} target="_blank" rel="noreferrer">
                {r.name} <ExternalLink aria-hidden="true" />
              </a>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

/** Grounding-check result as a small icon; the detail appears on hover/focus. */
export function ValidationIndicator({ validation }: { validation: ValidationEvent | undefined }) {
  if (!validation) return null;
  const unsupported = validation.unsupported_sentences ?? [];
  const invalid = validation.invalid_cites ?? [];
  const clean = validation.grounded && unsupported.length === 0 && invalid.length === 0;
  const title = clean
    ? "Every sentence of this answer was matched to a cited source."
    : validation.grounded
      ? "Parts of this answer could not be verified against the cited sources."
      : "Parts of this answer could not be matched to a source.";
  const shown = unsupported.slice(0, 4);
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="validation-indicator"
            data-state-tone={clean ? "positive" : "caution"}
            aria-label={clean ? "Grounding check passed" : "Grounding check: review needed"}
          >
            {clean ? <ShieldCheck aria-hidden="true" /> : <ShieldAlert aria-hidden="true" />}
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" align="start" className="validation-tooltip">
          <p className="validation-title">{title}</p>
          {shown.length > 0 && (
            <ul>
              {shown.map((s, i) => (
                <li key={i}>“{s}”</li>
              ))}
              {unsupported.length > shown.length && (
                <li className="validation-more">+{unsupported.length - shown.length} more</li>
              )}
            </ul>
          )}
          {invalid.length > 0 && (
            <p className="validation-foot">
              {invalid.length} citation marker{invalid.length === 1 ? "" : "s"} did not match a
              retrieved source.
            </p>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/** "{n} repealed provision(s) excluded as no longer in force". */
export function FilteredNote({ filtered }: { filtered: ChatMeta["filtered"] | undefined }) {
  const summary = filteredSummary(filtered);
  if (!summary) return null;
  return <p className="filtered-note">{summary}.</p>;
}

/** AGC attribution — required in small print wherever legislation text appears. */
export function Attribution({
  text,
  className,
}: {
  text?: string | undefined;
  className?: string;
}) {
  return (
    <p className={`attribution${className ? ` ${className}` : ""}`}>
      {text || FALLBACK_ATTRIBUTION}
    </p>
  );
}
