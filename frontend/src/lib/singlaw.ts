import { differenceInCalendarDays, formatDistanceStrict, isSameDay } from "date-fns";
import type {
  ChatMeta,
  ConversationDetail,
  ConversationMessage,
  ConversationSummary,
  FilteredCounts,
  Source,
  ValidationEvent,
} from "./api";
import { citeMarkersToLinks, splitPendingCite } from "./chat-stream";

// ---------------------------------------------------------------- message model

export interface MessageAttachment {
  id: string;
  filename: string;
}

/** A chat message as held in UI state: streamed live or loaded from the server. */
export interface UiMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  /** ISO timestamp. */
  createdAt: string;
  sources: Source[];
  meta?: ChatMeta | undefined;
  validation?: ValidationEvent | undefined;
  feedback?: "up" | "down" | null | undefined;
  attachments?: MessageAttachment[] | undefined;
  streaming?: boolean | undefined;
  /** Server-side message id used for feedback; differs from `id` while an answer streams. */
  serverId?: string | undefined;
  /** For assistant messages: the user question that produced this answer. */
  question?: string | undefined;
  /** Document scope active when the question was asked. */
  docIds?: string[] | null | undefined;
  error?: string | undefined;
  aborted?: boolean | undefined;
  /** Per-stage server timings (ms) from the `done` event or stored meta. */
  timings?: Record<string, number> | undefined;
}

type ServerMeta = ConversationMessage["meta"];

function isChatMeta(meta: ServerMeta): meta is ChatMeta & { validation?: ValidationEvent } {
  return (
    !!meta &&
    typeof meta === "object" &&
    ("temporal_basis" in meta || "conversation_id" in meta || "intent" in meta)
  );
}

/** Convert a stored server message into the UI model. */
export function fromServerMessage(m: ConversationMessage, question?: string): UiMessage {
  const message: UiMessage = {
    id: m.id,
    serverId: m.id,
    role: m.role,
    text: m.content ?? "",
    createdAt: m.created_at,
    sources: Array.isArray(m.sources) ? m.sources : [],
    feedback: m.feedback ?? null,
  };
  if (isChatMeta(m.meta)) {
    const { validation, ...meta } = m.meta;
    message.meta = meta;
    if (validation) message.validation = validation;
    const timings = (m.meta as { timings_ms?: unknown }).timings_ms;
    if (timings && typeof timings === "object") {
      message.timings = timings as Record<string, number>;
    }
  }
  if (m.role === "user") {
    // user turns persist their own attachments in meta.attachments
    const raw = (m.meta as { attachments?: unknown } | undefined)?.attachments;
    if (Array.isArray(raw)) {
      const attachments = raw.filter(
        (a): a is { id: string; filename: string } =>
          !!a && typeof a === "object" && typeof (a as { id?: unknown }).id === "string" &&
          typeof (a as { filename?: unknown }).filename === "string",
      );
      if (attachments.length) message.attachments = attachments;
    }
  }
  if (m.role === "assistant" && question !== undefined) message.question = question;
  return message;
}

/** Map a conversation's messages, pairing each answer with the question before it. */
export function messagesFromConversation(
  detail: Pick<ConversationDetail, "messages">,
): UiMessage[] {
  let lastQuestion: string | undefined;
  return detail.messages.map((m) => {
    if (m.role === "user") {
      lastQuestion = m.content;
      return fromServerMessage(m);
    }
    return fromServerMessage(m, lastQuestion);
  });
}

// ---------------------------------------------------------------- sidebar grouping

export type ConversationGroupLabel = "Today" | "Previous 7 days" | "Older";

export interface ConversationGroup {
  label: ConversationGroupLabel;
  items: ConversationSummary[];
}

function groupFor(updatedAt: string, now: Date): ConversationGroupLabel {
  const date = new Date(updatedAt);
  if (Number.isNaN(date.getTime())) return "Older";
  if (isSameDay(date, now)) return "Today";
  if (differenceInCalendarDays(now, date) <= 7) return "Previous 7 days";
  return "Older";
}

/** Sort newest first and bucket by `updated_at`; empty buckets are omitted. */
export function groupConversations(
  conversations: ConversationSummary[],
  now: Date = new Date(),
): ConversationGroup[] {
  const sorted = [...conversations].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );
  const buckets: Record<ConversationGroupLabel, ConversationSummary[]> = {
    Today: [],
    "Previous 7 days": [],
    Older: [],
  };
  for (const c of sorted) buckets[groupFor(c.updated_at, now)].push(c);
  return (["Today", "Previous 7 days", "Older"] as const)
    .filter((label) => buckets[label].length > 0)
    .map((label) => ({ label, items: buckets[label] }));
}

// ---------------------------------------------------------------- display helpers

export const TIER_NAMES: Record<number, string> = {
  1: "Constitution",
  2: "Act",
  3: "Subsidiary legislation",
  4: "Binding judgment",
  5: "Lower court",
  6: "Guidance",
};

export function tierName(tier: number): string {
  return TIER_NAMES[tier] ?? `Tier ${tier}`;
}

export function humanize(value: string): string {
  if (!value) return value;
  const spaced = value.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function statusLabel(status: string): string {
  switch (status) {
    case "in_force":
      return "In force";
    case "repealed":
      return "Repealed";
    case "spent":
      return "Spent";
    case "not_yet_commenced":
      return "Not yet commenced";
    case "amended":
      return "Amended";
    default:
      return humanize(status);
  }
}

export function docTypeLabel(docType: string): string {
  switch (docType) {
    case "act":
      return "Act";
    case "subsidiary_legislation":
      return "Subsidiary legislation";
    case "judgment":
      return "Judgment";
    case "practice_direction":
      return "Practice direction";
    case "constitution":
      return "Constitution";
    case "user_doc":
      return "Your document";
    default:
      return humanize(docType);
  }
}

const DATE_FMT = new Intl.DateTimeFormat("en-SG", {
  day: "numeric",
  month: "short",
  year: "numeric",
});
const DATETIME_FMT = new Intl.DateTimeFormat("en-SG", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** "11 Aug 2026" from an ISO date or timestamp; the raw value when unparseable. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return DATE_FMT.format(d);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return DATETIME_FMT.format(d);
}

/** "3 hours ago" style relative time. */
export function relativeTime(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return formatDistanceStrict(d, now, { addSuffix: true });
}

// ---------------------------------------------------------------- authority / trust

/** True when a source's status or treatment warrants a caution. */
export function isProblematic(status: string, treatment: string): boolean {
  return status !== "in_force" || treatment === "overruled";
}

export type Severity = "red" | "amber";

export function problemSeverity(status: string, treatment: string): Severity | null {
  if (status === "repealed" || treatment === "overruled") return "red";
  if (status !== "in_force") return "amber";
  return null;
}

/** Legislation (as opposed to judgments / user documents) attracts AGC attribution. */
export function isLegislation(docType: string, collection?: string): boolean {
  if (collection === "user_docs") return false;
  return docType !== "judgment" && docType !== "practice_direction" && docType !== "user_doc";
}

export function citesLegislation(sources: Source[]): boolean {
  return sources.some((s) => s.collection === "sg_law" && isLegislation(s.doc_type, s.collection));
}

/** Highest-authority (lowest tier) Singapore-law source; ties keep citation order. */
export function primarySource(sources: Source[]): Source | null {
  let primary: Source | null = null;
  for (const s of sources) {
    if (s.collection !== "sg_law") continue;
    if (primary === null || s.authority_tier < primary.authority_tier) primary = s;
  }
  return primary;
}

export interface AnswerWarning {
  severity: Severity;
  problems: string[];
}

/** The worst offender among cited authority drives the warning badge. */
export function answerWarning(sources: Source[]): AnswerWarning | null {
  let severity: Severity | null = null;
  const problems: string[] = [];
  for (const s of sources) {
    if (s.collection !== "sg_law" || !isProblematic(s.status, s.treatment)) continue;
    const sev = problemSeverity(s.status, s.treatment);
    if (sev === "red") severity = "red";
    else if (sev === "amber" && severity !== "red") severity = "amber";
    const why = s.treatment === "overruled" ? "overruled" : statusLabel(s.status).toLowerCase();
    problems.push(`${s.citation} (${why})`);
  }
  return severity ? { severity, problems } : null;
}

const LOW_CONFIDENCE_REASONS: Record<string, string> = {
  no_results: "nothing in the corpus answers this",
  all_results_filtered: "nothing in the corpus answers this",
  weak_relevance: "only weakly relevant sources were found",
  overruled_authority_in_top_results: "the top results include overruled authority",
  guidance_outranks_legislation: "guidance outranks legislation in the results",
};

/** One-line explanation for the low-confidence frame, varied by the backend's reason codes. */
export function lowConfidenceExplanation(reasons: string[] | undefined): string {
  const parts = [...new Set((reasons ?? []).map((r) => LOW_CONFIDENCE_REASONS[r] ?? humanize(r)))];
  const why =
    parts.length > 0 ? parts.join("; ") : "little strong authority was found for this question";
  return `Low confidence — ${why}. Read the cited sources before relying on this answer.`;
}

/** "2 repealed provisions excluded as no longer in force; …" or null when nothing was filtered. */
export function filteredSummary(filtered: FilteredCounts | undefined): string | null {
  if (!filtered) return null;
  const parts: string[] = [];
  const plural = (n: number) => (n === 1 ? "" : "s");
  if (filtered.repealed > 0)
    parts.push(
      `${filtered.repealed} repealed provision${plural(filtered.repealed)} excluded as no longer in force`,
    );
  if (filtered.spent > 0)
    parts.push(`${filtered.spent} spent provision${plural(filtered.spent)} excluded`);
  if (filtered.not_yet_commenced > 0)
    parts.push(
      `${filtered.not_yet_commenced} provision${plural(filtered.not_yet_commenced)} not yet in force excluded`,
    );
  return parts.length > 0 ? parts.join("; ") : null;
}

// ---------------------------------------------------------------- citations

/** `#cite-3` → 3; anything else → null. */
export function citeNumberFromHref(href: string | null | undefined): number | null {
  if (!href) return null;
  const m = /^#cite-(\d+)$/.exec(href.trim());
  return m?.[1] ? Number(m[1]) : null;
}

/** Markdown ready for the renderer: partial `[CITE:` tails held back while streaming. */
export function renderableAnswer(text: string, streaming: boolean): string {
  const visible = streaming ? splitPendingCite(text).renderable : text;
  return citeMarkersToLinks(visible);
}

/** Copy-friendly text: `[CITE:n]` becomes "(citation)"; unresolved markers are dropped. */
export function textForClipboard(text: string, sources: Source[]): string {
  return text.replace(/\s*\[CITE:(\d+)\]/g, (_m, num: string) => {
    const source = sources.find((s) => s.n === Number(num));
    return source ? ` (${source.citation})` : "";
  });
}

// ---------------------------------------------------------------- uploads

export const UPLOAD_EXTENSIONS = [".pdf", ".docx", ".txt", ".md"] as const;
export const UPLOAD_ACCEPT = UPLOAD_EXTENSIONS.join(",");
export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
export const UPLOAD_TYPE_MESSAGE =
  "Only PDF, Word (.docx), plain-text or Markdown files up to 25 MB can be analysed.";
export const DEFAULT_DOCUMENT_QUESTION = "What should I know about this document?";

export function isAllowedUpload(filename: string, size?: number): boolean {
  const lower = filename.toLowerCase();
  if (!UPLOAD_EXTENSIONS.some((ext) => lower.endsWith(ext))) return false;
  if (typeof size === "number" && size > MAX_UPLOAD_BYTES) return false;
  return true;
}

// ---------------------------------------------------------------- copy

export const SELECTED_BUSINESS_KEY = "singlaw.selectedBusiness";

export const DISCLAIMER_TEXT =
  "Legal information, not legal advice. Every answer cites the provisions and judgments it relies on — open a citation to read the source.";

export const FALLBACK_ATTRIBUTION =
  "Legislation is © Singapore Government, reproduced with the permission of the Attorney-General's Chambers under the SSO terms of use. Check https://sso.agc.gov.sg for the latest version; SSO downloads are not authoritative (s 48 Interpretation Act 1965) — the Gazette is.";

/** Official publishers behind the corpus; the public source library and workspace footer link here. */
export const sources = [
  {
    id: "employment",
    title: "Employment Act 1968",
    publisher: "Singapore Statutes Online",
    category: "Employment",
    description: "The statutory framework for employment rights and obligations in Singapore.",
    url: "https://sso.agc.gov.sg/Act/EmA1968",
  },
  {
    id: "mom",
    title: "Ministry of Manpower",
    publisher: "MOM",
    category: "Employment",
    description: "Official guidance on employment practices, leave and work passes.",
    url: "https://www.mom.gov.sg/employment-practices",
  },
  {
    id: "pdpa",
    title: "Personal Data Protection Act 2012",
    publisher: "Singapore Statutes Online",
    category: "Business",
    description: "The legal framework for the collection, use and disclosure of personal data.",
    url: "https://sso.agc.gov.sg/Act/PDPA2012",
  },
  {
    id: "customs",
    title: "Singapore Customs",
    publisher: "Singapore Customs",
    category: "Business",
    description: "Official information on permits, duties and importing goods.",
    url: "https://www.customs.gov.sg/businesses/importing-goods/",
  },
  {
    id: "hdb",
    title: "Housing & Development Board",
    publisher: "HDB",
    category: "Residency",
    description: "Official housing eligibility, buying and rental guidance.",
    url: "https://www.hdb.gov.sg/",
  },
  {
    id: "wildlife",
    title: "Wildlife Act 1965",
    publisher: "Singapore Statutes Online",
    category: "Everyday life",
    description: "The statutory framework for wildlife protection and management.",
    url: "https://sso.agc.gov.sg/Act/WA1965",
  },
];

export function metadata(title: string, description: string) {
  return {
    meta: [
      { title: `${title} — SingLaw` },
      { name: "description", content: description },
      { property: "og:title", content: `${title} — SingLaw` },
      { property: "og:description", content: description },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  };
}
