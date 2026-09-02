import { useCallback, useState } from 'react'
import type { ChatMeta, Source, ValidationEvent } from '../api'
import { formatDateTime, isLegislation } from '../lib/format'
import { AnswerStatusRow } from './AnswerStatusRow'
import { Attribution } from './Attribution'
import { MessageBody } from './MessageBody'
import { RetrievalInspector } from './RetrievalInspector'

/** A chat message as held in frontend state (streamed or loaded from history). */
export interface UiMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** ISO timestamp (from history, or stamped locally when sent). */
  createdAt: string | null
  sources: Source[]
  meta: ChatMeta | null
  validation: ValidationEvent | null
  streaming: boolean
  error: string | null
  aborted: boolean
  /** For assistant messages: the user question that produced this answer. */
  queryText: string | null
  /** Document scope active when the question was asked. */
  docIds: string[] | null
}

/**
 * Replace `[CITE:n]` markers with the actual legal citation in parentheses,
 * so copied text reads like a normal legal document.
 */
function contentForClipboard(content: string, sources: Source[]): string {
  return content.replace(/\s*\[CITE:(\d+)\]/g, (_, num: string) => {
    const source = sources.find((s) => s.n === Number(num))
    return source ? ` (${source.citation})` : ''
  })
}

function CopyButton({ content, sources }: { content: string; sources: Source[] }) {
  const [copied, setCopied] = useState(false)
  const copy = useCallback(() => {
    const text = contentForClipboard(content, sources)
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 2000)
      })
      .catch(() => {
        // Clipboard unavailable (e.g. insecure context) — nothing to do.
      })
  }, [content, sources])

  return (
    <button
      type="button"
      onClick={copy}
      title="Copy answer (citations written out in full)"
      className="inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] font-medium text-paper-600 transition-colors hover:bg-paper-100 hover:text-ink-900"
    >
      {copied ? (
        <>
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 fill-positive-600" aria-hidden="true">
            <path d="m6.5 12.1-4-4 1.2-1.2 2.8 2.8 5.8-5.8 1.2 1.2-7 7Z" />
          </svg>
          Copied
        </>
      ) : (
        <>
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 fill-current" aria-hidden="true">
            <path d="M5 2h8v9h-1.5V3.5H5V2ZM3 5h8v9H3V5Zm1.5 1.5v6h5v-6h-5Z" />
          </svg>
          Copy
        </>
      )}
    </button>
  )
}

export function ChatMessageView({ message }: { message: UiMessage }) {
  if (message.role === 'user') {
    return (
      <div className="group flex flex-col items-end">
        <div className="max-w-[85%] rounded-xl rounded-br-sm bg-ink-900 px-4 py-2.5 text-[15px] leading-6 whitespace-pre-wrap text-white shadow-card sm:max-w-[80%]">
          {message.content}
        </div>
        {message.createdAt && (
          <span className="mt-1 mr-1 text-[10px] text-paper-500 opacity-0 transition-opacity group-hover:opacity-100">
            {formatDateTime(message.createdAt)}
          </span>
        )}
      </div>
    )
  }

  const meta = message.meta
  const validation = message.validation
  const showValidationWarning =
    validation !== null && (!validation.grounded || validation.unsupported_sentences.length > 0)
  const citesLegislation = message.sources.some(
    (s) => s.collection === 'sg_law' && isLegislation(s.doc_type, s.collection),
  )

  const answerCore = (
    <>
      {meta?.high_stakes.triggered && (
        <div className="rounded-md border border-danger-300 bg-danger-50 p-3.5">
          <h4 className="text-sm font-semibold text-danger-900">
            This looks like a situation where you should speak to a professional
          </h4>
          {meta.high_stakes.reasons.length > 0 && (
            <p className="mt-1 text-xs text-danger-800">{meta.high_stakes.reasons.join(' · ')}</p>
          )}
          <ul className="mt-2 space-y-1">
            {meta.high_stakes.referrals.map((r) => (
              <li key={r.url}>
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-sm font-medium text-danger-900 underline underline-offset-2 hover:text-danger-700"
                >
                  {r.name}
                  <svg viewBox="0 0 16 16" className="h-3 w-3 fill-current" aria-hidden="true">
                    <path d="M6 3v1.5h4.4L3 11.9 4.1 13l7.4-7.4V10H13V3H6Z" />
                  </svg>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      <MessageBody
        content={message.content}
        streaming={message.streaming}
        sources={message.sources}
        invalidCites={validation?.invalid_cites}
      />

      {message.aborted && (
        <p className="text-xs text-paper-600 italic">
          Generation stopped by you — answer is incomplete.
        </p>
      )}

      {message.error && (
        <p className="rounded-md border border-danger-300 bg-danger-50 px-3 py-2 text-sm text-danger-800">
          {message.error}
        </p>
      )}

      {showValidationWarning && validation && (
        <div className="rounded-md border border-caution-400 bg-caution-50 p-3">
          <h4 className="text-xs font-semibold text-caution-900">
            {validation.grounded
              ? 'Parts of this answer could not be verified against the cited sources'
              : 'This answer failed grounding validation — treat it with caution'}
          </h4>
          {validation.unsupported_sentences.length > 0 && (
            <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs text-caution-900">
              {validation.unsupported_sentences.map((s, i) => (
                <li key={i} className="italic">
                  “{s}”
                </li>
              ))}
            </ul>
          )}
          {validation.invalid_cites.length > 0 && (
            <p className="mt-1.5 text-xs text-caution-900">
              {validation.invalid_cites.length} citation marker
              {validation.invalid_cites.length > 1 ? 's' : ''} did not match any retrieved source
              (highlighted in red above).
            </p>
          )}
        </div>
      )}
    </>
  )

  return (
    <div className="group space-y-2.5">
      {meta?.low_confidence ? (
        <div className="space-y-2.5 rounded-md border-2 border-dashed border-caution-400 bg-caution-50/60 p-3.5">
          <div className="flex items-start gap-2 border-b border-caution-300 pb-2.5">
            <svg
              viewBox="0 0 16 16"
              className="mt-0.5 h-4 w-4 shrink-0 fill-caution-600"
              aria-hidden="true"
            >
              <path d="M8 1.5 15.2 14H.8L8 1.5Zm-.75 4.5v4h1.5V6h-1.5Zm0 5v1.5h1.5V11h-1.5Z" />
            </svg>
            <p className="text-xs leading-5 text-caution-900">
              <span className="font-semibold">Low confidence.</span> The system could not find
              strong authority for this question in its corpus. What follows may be incomplete or
              off-point — verify against the cited sources and consider consulting a lawyer.
            </p>
          </div>
          {answerCore}
        </div>
      ) : (
        answerCore
      )}

      {!message.streaming && (message.sources.length > 0 || meta) && (
        <AnswerStatusRow sources={message.sources} meta={meta} />
      )}

      {!message.streaming && !message.error && message.content && (
        <div className="flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
          <CopyButton content={message.content} sources={message.sources} />
          {message.createdAt && (
            <span className="text-[10px] text-paper-500">{formatDateTime(message.createdAt)}</span>
          )}
        </div>
      )}

      {!message.streaming && citesLegislation && (
        <Attribution text={meta?.attribution || undefined} />
      )}

      {!message.streaming && !message.error && message.queryText && (
        <RetrievalInspector query={message.queryText} docIds={message.docIds} />
      )}
    </div>
  )
}
