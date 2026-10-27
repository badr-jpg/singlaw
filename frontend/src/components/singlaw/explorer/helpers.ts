/**
 * Pure helpers for the corpus explorer (/sources, /sources/$docId).
 * Everything here is side-effect free so it can be unit tested without the DOM.
 */
import type { DocTreeNode, HealthResponse } from "@/lib/api";

// ---------------------------------------------------------------- doc types

export type DocTypeFilter =
  "all" | "act" | "subsidiary_legislation" | "judgment" | "practice_direction";

export const DOC_TYPE_TABS: ReadonlyArray<{ value: DocTypeFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "act", label: "Acts" },
  { value: "subsidiary_legislation", label: "Subsidiary legislation" },
  { value: "judgment", label: "Judgments" },
  { value: "practice_direction", label: "Practice directions" },
];

export function isDocTypeFilter(value: unknown): value is DocTypeFilter {
  return DOC_TYPE_TABS.some((t) => t.value === value);
}

export function docTypeLabel(docType: string | null | undefined): string {
  switch (docType) {
    case "act":
      return "Act";
    case "subsidiary_legislation":
      return "Subsidiary legislation";
    case "judgment":
      return "Judgment";
    case "practice_direction":
      return "Practice direction";
    case "user_document":
      return "Your document";
    default:
      return docType ? docType.replace(/_/g, " ") : "Document";
  }
}

export function isLegislation(docType: string | null | undefined): boolean {
  return docType === "act" || docType === "subsidiary_legislation";
}

// ---------------------------------------------------------------- authority tiers

export const TIER_NAMES: Readonly<Record<number, string>> = {
  1: "Constitution",
  2: "Act",
  3: "Subsidiary legislation",
  4: "Binding judgment",
  5: "Lower court",
  6: "Guidance",
};

export function tierName(tier: number | null | undefined): string {
  return (tier != null && TIER_NAMES[tier]) || "Unranked";
}

export function tierLabel(tier: number | null | undefined): string {
  const name = tierName(tier);
  return tier != null && TIER_NAMES[tier] ? `Tier ${tier} · ${name}` : name;
}

// ---------------------------------------------------------------- status & treatment

export type Tone = "ok" | "caution" | "danger" | "muted" | "brand";

function humanise(value: string): string {
  const words = value.replace(/_/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : "";
}

/** Legislation status as the backend records it (`in_force`, `repealed`, ...). */
export function statusLabel(status: string | null | undefined): string {
  switch (status) {
    case "in_force":
      return "In force";
    case "repealed":
      return "Repealed";
    case "spent":
      return "Spent";
    case "not_yet_commenced":
      return "Not yet commenced";
    case "n_a":
    case null:
    case undefined:
    case "":
      return "";
    default:
      return humanise(status);
  }
}

export function statusTone(status: string | null | undefined): Tone {
  switch (status) {
    case "in_force":
      return "ok";
    case "repealed":
      return "danger";
    case "spent":
    case "not_yet_commenced":
      return "caution";
    default:
      return "muted";
  }
}

/**
 * Judicial treatment of a judgment (from the citation graph). `unknown` and
 * `neutral` carry no signal, so they render nothing; the caller hides nulls.
 */
export function treatmentLabel(treatment: string | null | undefined): string | null {
  switch (treatment) {
    case "overruled":
      return "Overruled";
    case "distinguished":
      return "Distinguished";
    case "good":
      return "Good law";
    case "neutral":
      return "Cited";
    default:
      return null;
  }
}

export function treatmentTone(treatment: string | null | undefined): Tone {
  switch (treatment) {
    case "overruled":
      return "danger";
    case "distinguished":
      return "caution";
    case "good":
      return "ok";
    default:
      return "muted";
  }
}

/** True when the authority should be visibly flagged rather than silently served. */
export function isFlagged(status: string | null | undefined, treatment: string | null | undefined) {
  return status === "repealed" || treatment === "overruled";
}

// ---------------------------------------------------------------- ids & links

/** Chunk ids are `<doc_id>:<locator>` (e.g. `employment-act-1968:s14`). */
export function docIdFromChunkId(chunkId: string): string {
  const i = chunkId.indexOf(":");
  return i === -1 ? chunkId : chunkId.slice(0, i);
}

/**
 * The chat workspace owns `/`; it is asked to honour a `?q=` search param so a
 * provision can be handed over as a ready-to-send question.
 */
export function askAboutQuestion(citation: string): string {
  return `What does ${citation} say?`;
}

export function askAboutUrl(citation: string): string {
  return `/?q=${encodeURIComponent(askAboutQuestion(citation))}`;
}

// ---------------------------------------------------------------- formatting

const dateFormat = new Intl.DateTimeFormat("en-SG", {
  day: "numeric",
  month: "short",
  year: "numeric",
});
const dateTimeFormat = new Intl.DateTimeFormat("en-SG", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function parseDate(value: string): Date | null {
  const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const d = parseDate(value);
  return d ? dateFormat.format(d) : value;
}

export function formatDateTime(value: string | null | undefined): string | null {
  if (!value) return null;
  const d = parseDate(value);
  return d ? dateTimeFormat.format(d) : value;
}

export function formatCount(n: number): string {
  return n.toLocaleString("en-SG");
}

export function plural(n: number, one: string, many: string = `${one}s`): string {
  return `${formatCount(n)} ${n === 1 ? one : many}`;
}

/** "412 Acts · 1,208 subsidiary legislation · 3,410 judgments · 12 practice directions · synced 7 Oct 2026" */
export function corpusSummary(health: Pick<HealthResponse, "corpus" | "last_sync">): string {
  const c = health.corpus;
  const parts = [
    plural(c.acts, "Act"),
    `${formatCount(c.subsidiary_legislation)} subsidiary legislation`,
    plural(c.judgments, "judgment"),
    plural(c.practice_directions, "practice direction"),
  ];
  const synced = formatDate(health.last_sync);
  parts.push(synced ? `synced ${synced}` : "not synced yet");
  return parts.join(" · ");
}

/** Scores from the ranker are 0–1 blends; clamp defensively for the meters. */
export function scorePercent(score: number | null | undefined): number {
  if (score == null || Number.isNaN(score)) return 0;
  return Math.round(Math.min(1, Math.max(0, score)) * 100);
}

export function formatScore(score: number | null | undefined): string {
  if (score == null || Number.isNaN(score)) return "–";
  return score.toFixed(2);
}

// ---------------------------------------------------------------- document tree

export function isLeaf(node: DocTreeNode): boolean {
  return node.chunk_id !== null && node.children.length === 0;
}

export function flattenLeaves(tree: ReadonlyArray<DocTreeNode>): DocTreeNode[] {
  const out: DocTreeNode[] = [];
  const walk = (nodes: ReadonlyArray<DocTreeNode>) => {
    for (const node of nodes) {
      if (node.chunk_id) out.push(node);
      if (node.children.length) walk(node.children);
    }
  };
  walk(tree);
  return out;
}

export function firstLeaf(tree: ReadonlyArray<DocTreeNode>): DocTreeNode | null {
  return flattenLeaves(tree)[0] ?? null;
}

export function findLeaf(tree: ReadonlyArray<DocTreeNode>, chunkId: string): DocTreeNode | null {
  return flattenLeaves(tree).find((n) => n.chunk_id === chunkId) ?? null;
}

/** Stable key for a node from its index path, e.g. `0.2.1`. */
export function nodeKey(path: ReadonlyArray<number>): string {
  return path.join(".");
}

/** Keys of every ancestor group of the leaf holding `chunkId` (for auto-expanding the outline). */
export function ancestorKeys(tree: ReadonlyArray<DocTreeNode>, chunkId: string): string[] {
  const found: string[] = [];
  const walk = (nodes: ReadonlyArray<DocTreeNode>, path: number[]): boolean => {
    for (let i = 0; i < nodes.length; i++) {
      const node = nodes[i]!;
      const here = [...path, i];
      if (node.chunk_id === chunkId) return true;
      if (node.children.length && walk(node.children, here)) {
        found.unshift(nodeKey(here));
        return true;
      }
    }
    return false;
  };
  walk(tree, []);
  return found;
}

/** Leaf position (1-based) and total, for "Section 3 of 120"-style hints. */
export function leafPosition(
  tree: ReadonlyArray<DocTreeNode>,
  chunkId: string,
): { index: number; total: number } | null {
  const leaves = flattenLeaves(tree);
  const i = leaves.findIndex((n) => n.chunk_id === chunkId);
  return i === -1 ? null : { index: i + 1, total: leaves.length };
}

export function neighbourLeaves(
  tree: ReadonlyArray<DocTreeNode>,
  chunkId: string,
): { previous: DocTreeNode | null; next: DocTreeNode | null } {
  const leaves = flattenLeaves(tree);
  const i = leaves.findIndex((n) => n.chunk_id === chunkId);
  if (i === -1) return { previous: null, next: null };
  return { previous: leaves[i - 1] ?? null, next: leaves[i + 1] ?? null };
}

/**
 * Cross-encoder scores may arrive as raw logits (the backend applies a sigmoid
 * only when deciding confidence), so map anything outside 0–1 through a sigmoid
 * before drawing a meter. The raw number is still shown beside it.
 */
export function normaliseScore(score: number | null | undefined): number {
  if (score == null || Number.isNaN(score)) return 0;
  if (score >= 0 && score <= 1) return score;
  return 1 / (1 + Math.exp(-score));
}

/**
 * Judgments and practice directions are stored as `in_force` for filtering
 * purposes; that label means nothing to a reader, so only legislation shows it.
 */
export function showStatus(docType: string | null | undefined, status: string | null | undefined) {
  return isLegislation(docType) || (status !== "in_force" && statusLabel(status) !== "");
}
