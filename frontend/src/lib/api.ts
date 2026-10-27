/**
 * Typed client for the SingLaw backend (FastAPI).
 * Shapes mirror docs/superpowers/plans/2026-08-11-sg-law-rag.md — the v1
 * contract plus the v2 addendum (conversations create, businesses, feedback,
 * content, billing). Keep this file in sync with that document.
 */

// ---------------------------------------------------------------- sources

export interface Source {
  n: number;
  chunk_id: string;
  citation: string;
  url: string;
  doc_type: string;
  authority_tier: number;
  status: string;
  treatment: string;
  court: string | null;
  decision_date: string | null;
  hierarchy_path: string[];
  snippet: string;
  collection: "sg_law" | "user_docs";
}

export interface Chunk extends Source {
  text: string;
  context: string;
  doc_id: string;
}

// ---------------------------------------------------------------- chat SSE

export type ChatIntent =
  | "statutory_lookup"
  | "procedural"
  | "rights_obligations"
  | "case_law"
  | "out_of_scope"
  | "drafting_refused";

export interface FilteredCounts {
  repealed: number;
  spent: number;
  not_yet_commenced: number;
}

export interface HighStakesReferral {
  name: string;
  url: string;
}

export interface ChatMeta {
  conversation_id: string;
  message_id: string;
  intent: ChatIntent;
  low_confidence: boolean;
  low_confidence_reasons?: string[];
  filtered: FilteredCounts;
  temporal_basis: string;
  high_stakes: { triggered: boolean; reasons: string[]; referrals: HighStakesReferral[] };
  attribution: string;
  disclaimer: string;
  corpus_last_synced: string | null;
  business_id?: string | null;
}

export interface SourcesEvent {
  sources: Source[];
}
export interface TokenEvent {
  text: string;
}
export interface ValidationEvent {
  grounded: boolean;
  unsupported_sentences: string[];
  invalid_cites: number[];
}
export interface DoneEvent {
  message_id: string;
  finish_reason: string;
  timings_ms?: Record<string, number>;
}
export interface ErrorEvent {
  message: string;
}

export interface ChatRequest {
  message: string;
  conversation_id: string | null;
  doc_ids?: string[] | null;
  business_id?: string | null;
  regenerate?: boolean;
}

// ---------------------------------------------------------------- conversations

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  sources: Source[];
  meta: (ChatMeta & { validation?: ValidationEvent }) | Record<string, never>;
  feedback?: "up" | "down" | null;
}

export interface ConversationDetail {
  id: string;
  title: string;
  messages: ConversationMessage[];
}

// ---------------------------------------------------------------- documents

export type DocumentStatus = "pending" | "processing" | "ready" | "error";

export interface UploadedDocument {
  id: string;
  filename: string;
  status: DocumentStatus;
  chunk_count: number;
  error: string | null;
  created_at: string;
  business_id?: string | null;
}

export interface UploadResponse {
  id: string;
  filename: string;
  status: "pending";
}

// ---------------------------------------------------------------- businesses

export interface Business {
  id: string;
  name: string;
  description: string;
  icon: string;
  document_count: number;
  created_at: string;
}

// ---------------------------------------------------------------- search

export interface SearchRequest {
  query: string;
  top_k?: number;
  include_debug?: boolean;
  doc_ids?: string[] | null;
  business_id?: string | null;
}

export interface SearchResult extends Source {
  text: string;
  pinned?: boolean;
  rrf_score?: number;
  ce_score: number;
  authority_score: number;
  final_score: number;
}

export interface SearchCandidate {
  chunk_id: string;
  citation: string;
  rrf_score: number;
}

export interface SearchDebug {
  rewrites: string[];
  hyde: string | null;
  citation_shortcircuit: string[];
  candidates_pre_filter: number;
  candidates_pre_rerank: SearchCandidate[];
  timings_ms: Record<string, number>;
}

export interface SearchResponse {
  results: SearchResult[];
  low_confidence: boolean;
  low_confidence_reasons?: string[];
  filtered: FilteredCounts;
  intent?: ChatIntent;
  debug: SearchDebug | null;
}

// ---------------------------------------------------------------- law / corpus

export interface LawLookupResponse {
  found: boolean;
  chunks: Chunk[];
}
export interface LawVersion {
  sso_version_date: string | null;
  fetched_at: string;
  source_url: string;
}
export interface LawHistoryResponse {
  versions: LawVersion[];
}
export interface CitingJudgment {
  citation: string;
  case_name?: string | null;
  court: string | null;
  decision_date: string | null;
  treatment: string;
  paragraph?: number | null;
}
export interface LawCitingResponse {
  citing: CitingJudgment[];
}
export interface TocEntry {
  doc_id: string;
  title: string;
  citation: string;
  doc_type: string;
  status: string;
  authority_tier: number;
}
export interface DocTreeNode {
  label: string;
  citation: string | null;
  chunk_id: string | null;
  children: DocTreeNode[];
}
export interface CorpusDoc {
  doc_id: string;
  title: string;
  citation: string;
  doc_type: string;
  status: string;
  source_url: string;
  sso_version_date: string | null;
  tree: DocTreeNode[];
}

// ---------------------------------------------------------------- content

export interface Suggestion {
  label: string;
  text: string;
}
export interface Discovery {
  id: string;
  title: string;
  body: string;
  question: string;
  citation: string;
  url: string;
}

// ---------------------------------------------------------------- billing

export interface Plan {
  id: string;
  name: string;
  description: string;
  price_monthly_sgd: number | null;
  price_yearly_sgd: number | null;
  features: string[];
  limits: { businesses: number | null; documents: number | null };
  featured: boolean;
  available: boolean;
}
export interface BillingStatus {
  plan: string;
  usage: { conversations: number; messages: number; documents: number; businesses: number };
  limits: { businesses: number | null; documents: number | null };
  checkout_available: boolean;
}

// ---------------------------------------------------------------- ops

export interface HealthResponse {
  status: "ok" | "degraded";
  models: { embedder: string; reranker: string; loaded: boolean };
  qdrant: { sg_law: number; user_docs: number };
  corpus: {
    acts: number;
    subsidiary_legislation: number;
    judgments: number;
    practice_directions: number;
    repealed: number;
  };
  llm: { provider: string; configured: boolean };
  last_sync: string | null;
}

// ---------------------------------------------------------------- http

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, "Cannot reach SingLaw right now. Please try again in a moment.");
  }
  if (!res.ok) {
    let detail = "";
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object") {
        const d = (body as Record<string, unknown>)["detail"] ?? (body as Record<string, unknown>)["message"];
        if (typeof d === "string") detail = d;
      }
    } catch {
      // non-JSON error body
    }
    throw new ApiError(res.status, detail || `Request failed (${res.status} ${res.statusText})`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
const enc = encodeURIComponent;

// ---------------------------------------------------------------- client

export const api = {
  // conversations
  listConversations: () => http<ConversationSummary[]>("/api/conversations"),
  createConversation: (title?: string) =>
    http<ConversationSummary>("/api/conversations", json("POST", { title: title ?? null })),
  getConversation: (id: string) => http<ConversationDetail>(`/api/conversations/${enc(id)}`),
  renameConversation: (id: string, title: string) =>
    http<unknown>(`/api/conversations/${enc(id)}`, json("PATCH", { title })),
  deleteConversation: (id: string) =>
    http<void>(`/api/conversations/${enc(id)}`, { method: "DELETE" }),

  // documents
  uploadDocument: (file: File, businessId?: string | null) => {
    const form = new FormData();
    form.append("file", file);
    if (businessId) form.append("business_id", businessId);
    return http<UploadResponse>("/api/documents", { method: "POST", body: form });
  },
  listDocuments: () => http<UploadedDocument[]>("/api/documents"),
  deleteDocument: (id: string) => http<void>(`/api/documents/${enc(id)}`, { method: "DELETE" }),

  // businesses
  listBusinesses: () => http<Business[]>("/api/businesses"),
  createBusiness: (body: { name: string; description?: string; icon?: string }) =>
    http<Business>("/api/businesses", json("POST", body)),
  updateBusiness: (id: string, body: Partial<Pick<Business, "name" | "description" | "icon">>) =>
    http<Business>(`/api/businesses/${enc(id)}`, json("PATCH", body)),
  deleteBusiness: (id: string) => http<void>(`/api/businesses/${enc(id)}`, { method: "DELETE" }),
  listBusinessDocuments: (id: string) =>
    http<UploadedDocument[]>(`/api/businesses/${enc(id)}/documents`),

  // feedback
  sendFeedback: (messageId: string, rating: "up" | "down", comment?: string) =>
    http<{ ok: boolean }>(
      "/api/feedback",
      json("POST", { message_id: messageId, rating, comment: comment ?? null }),
    ),

  // content
  suggestions: (mode: "personal" | "business") =>
    http<{ suggestions: Suggestion[] }>(`/api/content/suggestions?mode=${mode}`),
  discoveries: () => http<{ discoveries: Discovery[] }>("/api/content/discoveries"),

  // search / law / corpus
  search: (req: SearchRequest) => http<SearchResponse>("/api/search", json("POST", req)),
  getLaw: (citation: string) => http<LawLookupResponse>(`/api/law/${enc(citation)}`),
  getLawHistory: (citation: string) =>
    http<LawHistoryResponse>(`/api/law/${enc(citation)}/history`),
  getLawCiting: (citation: string) => http<LawCitingResponse>(`/api/law/${enc(citation)}/citing`),
  corpusToc: (params: { doc_type?: string; q?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.doc_type) qs.set("doc_type", params.doc_type);
    if (params.q) qs.set("q", params.q);
    const s = qs.toString();
    return http<TocEntry[]>(`/api/corpus/toc${s ? `?${s}` : ""}`);
  },
  corpusDoc: (docId: string) => http<CorpusDoc>(`/api/corpus/doc/${enc(docId)}`),
  getChunk: (chunkId: string) => http<Chunk>(`/api/chunks/${enc(chunkId)}`),

  // billing
  plans: () => http<{ plans: Plan[] }>("/api/billing/plans"),
  billingStatus: () => http<BillingStatus>("/api/billing/status"),
  checkout: (planId: string, interval: "monthly" | "yearly") =>
    http<{ url: string }>("/api/billing/checkout", json("POST", { plan_id: planId, interval })),
  joinWaitlist: (email: string, planId: string) =>
    http<{ ok: boolean }>("/api/billing/waitlist", json("POST", { email, plan_id: planId })),

  // ops
  health: () => http<HealthResponse>("/api/health"),
};

export type Api = typeof api;
