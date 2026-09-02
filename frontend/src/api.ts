/**
 * Typed API client for the SG Law RAG backend.
 * All types mirror the frozen API contract in
 * docs/superpowers/plans/2026-08-11-sg-law-rag.md exactly.
 */

// ---------------------------------------------------------------------------
// Shared source / chunk shapes
// ---------------------------------------------------------------------------

export interface Source {
  n: number
  chunk_id: string
  citation: string
  url: string
  doc_type: string
  authority_tier: number
  status: string
  treatment: string
  court: string | null
  decision_date: string | null
  hierarchy_path: string[]
  snippet: string
  collection: 'sg_law' | 'user_docs'
}

export interface Chunk extends Source {
  text: string
  context: string
  doc_id: string
}

// ---------------------------------------------------------------------------
// Chat SSE event payloads
// ---------------------------------------------------------------------------

export type ChatIntent =
  | 'statutory_lookup'
  | 'procedural'
  | 'rights_obligations'
  | 'case_law'
  | 'out_of_scope'
  | 'drafting_refused'

export interface FilteredCounts {
  repealed: number
  spent: number
  not_yet_commenced: number
}

export interface HighStakesReferral {
  name: string
  url: string
}

export interface ChatMeta {
  conversation_id: string
  message_id: string
  intent: ChatIntent
  low_confidence: boolean
  filtered: FilteredCounts
  temporal_basis: string
  high_stakes: {
    triggered: boolean
    reasons: string[]
    referrals: HighStakesReferral[]
  }
  attribution: string
  disclaimer: string
  corpus_last_synced: string | null
}

export interface SourcesEvent {
  sources: Source[]
}

export interface TokenEvent {
  text: string
}

export interface ValidationEvent {
  grounded: boolean
  unsupported_sentences: string[]
  invalid_cites: number[]
}

export interface DoneEvent {
  message_id: string
  finish_reason: string
}

export interface ErrorEvent {
  message: string
}

export interface ChatRequest {
  message: string
  conversation_id: string | null
  doc_ids: string[] | null
}

// ---------------------------------------------------------------------------
// Conversations
// ---------------------------------------------------------------------------

export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface ConversationMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  sources: Source[]
  meta: ChatMeta | null
}

export interface ConversationDetail {
  id: string
  title: string
  messages: ConversationMessage[]
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'error'

export interface UploadedDocument {
  id: string
  filename: string
  status: DocumentStatus
  chunk_count: number
  error: string | null
  created_at: string
}

export interface UploadResponse {
  id: string
  filename: string
  status: 'pending'
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export interface SearchRequest {
  query: string
  top_k?: number
  include_debug?: boolean
  doc_ids?: string[] | null
}

export interface SearchResult extends Source {
  text: string
  ce_score: number
  authority_score: number
  final_score: number
}

export interface SearchCandidate {
  chunk_id: string
  citation: string
  rrf_score: number
}

export interface SearchDebug {
  rewrites: string[]
  hyde: string | null
  citation_shortcircuit: string[]
  candidates_pre_filter: number
  candidates_pre_rerank: SearchCandidate[]
  timings_ms: Record<string, number>
}

export interface SearchResponse {
  results: SearchResult[]
  low_confidence: boolean
  filtered: FilteredCounts
  debug: SearchDebug | null
}

// ---------------------------------------------------------------------------
// Law / corpus explorer
// ---------------------------------------------------------------------------

export interface LawLookupResponse {
  found: boolean
  chunks: (Source & { text: string })[]
}

export interface LawVersion {
  sso_version_date: string
  fetched_at: string
  source_url: string
}

export interface LawHistoryResponse {
  versions: LawVersion[]
}

export interface CitingJudgment {
  citation: string
  court: string
  decision_date: string
  treatment: string
}

export interface LawCitingResponse {
  citing: CitingJudgment[]
}

export interface TocEntry {
  doc_id: string
  title: string
  citation: string
  doc_type: string
  status: string
  authority_tier: number
}

export interface DocTreeNode {
  label: string
  citation: string
  chunk_id: string | null
  children: DocTreeNode[]
}

export interface CorpusDoc {
  doc_id: string
  title: string
  citation: string
  status: string
  source_url: string
  sso_version_date: string
  tree: DocTreeNode[]
}

// ---------------------------------------------------------------------------
// Ops
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: 'ok' | 'degraded'
  models: { embedder: string; reranker: string; loaded: boolean }
  qdrant: { sg_law: number; user_docs: number }
  corpus: {
    acts: number
    subsidiary_legislation: number
    judgments: number
    practice_directions: number
    repealed: number
  }
  llm: { provider: string; configured: boolean }
  last_sync: string | null
}

export interface SyncResponse {
  started: boolean
  reason: string
}

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'Cannot reach the backend. Is the server running?')
  }
  if (!res.ok) {
    let detail = ''
    try {
      const body: unknown = await res.json()
      if (body && typeof body === 'object') {
        const rec = body as Record<string, unknown>
        const d = rec['detail'] ?? rec['message']
        if (typeof d === 'string') detail = d
      }
    } catch {
      // non-JSON error body; fall through to the generic message
    }
    throw new ApiError(res.status, detail || `Request failed (${res.status} ${res.statusText})`)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

// ---------------------------------------------------------------------------
// Client functions (one per endpoint)
// ---------------------------------------------------------------------------

// Conversations
export function listConversations(): Promise<ConversationSummary[]> {
  return http('/api/conversations')
}

export function getConversation(id: string): Promise<ConversationDetail> {
  return http(`/api/conversations/${encodeURIComponent(id)}`)
}

export function renameConversation(id: string, title: string): Promise<unknown> {
  return http(`/api/conversations/${encodeURIComponent(id)}`, jsonInit('PATCH', { title }))
}

export function deleteConversation(id: string): Promise<void> {
  return http(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// Documents
export function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  return http('/api/documents', { method: 'POST', body: form })
}

export function listDocuments(): Promise<UploadedDocument[]> {
  return http('/api/documents')
}

export function deleteDocument(id: string): Promise<void> {
  return http(`/api/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// Search
export function search(req: SearchRequest): Promise<SearchResponse> {
  return http('/api/search', jsonInit('POST', req))
}

// Law / corpus
export function getLaw(citation: string): Promise<LawLookupResponse> {
  return http(`/api/law/${encodeURIComponent(citation)}`)
}

export function getLawHistory(citation: string): Promise<LawHistoryResponse> {
  return http(`/api/law/${encodeURIComponent(citation)}/history`)
}

export function getLawCiting(citation: string): Promise<LawCitingResponse> {
  return http(`/api/law/${encodeURIComponent(citation)}/citing`)
}

export function getCorpusToc(params: { doc_type?: string; q?: string }): Promise<TocEntry[]> {
  const qs = new URLSearchParams()
  if (params.doc_type) qs.set('doc_type', params.doc_type)
  if (params.q) qs.set('q', params.q)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return http(`/api/corpus/toc${suffix}`)
}

export function getCorpusDoc(docId: string): Promise<CorpusDoc> {
  return http(`/api/corpus/doc/${encodeURIComponent(docId)}`)
}

export function getChunk(chunkId: string): Promise<Chunk> {
  return http(`/api/chunks/${encodeURIComponent(chunkId)}`)
}

// Ops
export function getHealth(): Promise<HealthResponse> {
  return http('/api/health')
}

export function adminSync(force = false): Promise<SyncResponse> {
  return http('/api/admin/sync', jsonInit('POST', { force }))
}
