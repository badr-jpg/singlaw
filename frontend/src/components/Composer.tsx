import { useEffect, useRef, useState } from 'react'
import { listDocuments } from '../api'
import type { UploadedDocument } from '../api'
import { useToast } from '../context/ToastContext'

export interface DocScopeEntry {
  id: string
  filename: string
}

interface Props {
  streaming: boolean
  onSend: (text: string) => void
  onStop: () => void
  docScope: DocScopeEntry[]
  onAddDoc: (doc: DocScopeEntry) => void
  onRemoveDoc: (id: string) => void
}

/**
 * Chat composer: Enter sends, Shift+Enter inserts a newline; disabled while
 * streaming with a stop affordance. When document scope is active a removable
 * chip row appears above the textarea, and a picker lets the user scope the
 * question to uploaded documents.
 */
export function Composer({ streaming, onSend, onStop, docScope, onAddDoc, onRemoveDoc }: Props) {
  const toast = useToast()
  const [text, setText] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerDocs, setPickerDocs] = useState<UploadedDocument[] | null>(null)
  const [pickerLoading, setPickerLoading] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const pickerRef = useRef<HTMLDivElement>(null)

  const submit = () => {
    const trimmed = text.trim()
    if (!trimmed || streaming) return
    onSend(trimmed)
    setText('')
  }

  const openPicker = () => {
    const next = !pickerOpen
    setPickerOpen(next)
    if (next) {
      setPickerLoading(true)
      listDocuments()
        .then((docs) => setPickerDocs(docs.filter((d) => d.status === 'ready')))
        .catch((e: unknown) => {
          toast.push(e instanceof Error ? e.message : 'Failed to load documents.')
          setPickerOpen(false)
        })
        .finally(() => setPickerLoading(false))
    }
  }

  useEffect(() => {
    if (!pickerOpen) return
    const onClick = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setPickerOpen(false)
      }
    }
    window.addEventListener('mousedown', onClick)
    return () => window.removeEventListener('mousedown', onClick)
  }, [pickerOpen])

  return (
    <div className="border-t border-paper-200 bg-paper-25 px-4 py-3">
      {docScope.length > 0 && (
        <div className="mx-auto mb-2 flex max-w-3xl flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-medium text-paper-600">
            Answering with reference to your document{docScope.length > 1 ? 's' : ''}:
          </span>
          {docScope.map((d) => (
            <span
              key={d.id}
              className="inline-flex items-center gap-1 rounded-full border border-scope-300 bg-scope-50 px-2 py-0.5 text-[11px] font-medium text-scope-900"
            >
              {d.filename}
              <button
                type="button"
                onClick={() => onRemoveDoc(d.id)}
                aria-label={`Remove ${d.filename} from scope`}
                className="text-scope-500 hover:text-scope-900"
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <div className="relative" ref={pickerRef}>
          <button
            type="button"
            onClick={openPicker}
            title="Ask about an uploaded document"
            aria-label="Scope question to an uploaded document"
            aria-expanded={pickerOpen}
            className="rounded-md border border-paper-300 bg-white p-2.5 text-paper-600 transition-colors hover:border-ink-300 hover:bg-ink-50 hover:text-ink-800"
          >
            <svg viewBox="0 0 16 16" className="h-4 w-4 fill-current" aria-hidden="true">
              <path d="M9.5 1H3.75A.75.75 0 0 0 3 1.75v12.5c0 .41.34.75.75.75h8.5a.75.75 0 0 0 .75-.75V4.5L9.5 1Zm0 2.1 1.9 1.9H9.5V3.1ZM5 7h6v1.2H5V7Zm0 2.5h6v1.2H5V9.5Z" />
            </svg>
          </button>
          {pickerOpen && (
            <div className="absolute bottom-full left-0 z-20 mb-1.5 w-72 rounded-md border border-paper-300 bg-white p-1 shadow-pop">
              <p className="px-2 py-1 text-[11px] font-semibold tracking-wide text-paper-600 uppercase">
                Ask about a document
              </p>
              {pickerLoading && <p className="px-2 py-1.5 text-xs text-paper-600">Loading…</p>}
              {!pickerLoading && pickerDocs && pickerDocs.length === 0 && (
                <p className="px-2 py-1.5 text-xs text-paper-600">
                  No processed documents. Upload one on the Documents page.
                </p>
              )}
              {!pickerLoading &&
                pickerDocs?.map((d) => {
                  const inScope = docScope.some((s) => s.id === d.id)
                  return (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => {
                        if (inScope) onRemoveDoc(d.id)
                        else onAddDoc({ id: d.id, filename: d.filename })
                      }}
                      className="flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-left text-xs text-ink-800 transition-colors hover:bg-paper-100"
                    >
                      <span className="truncate">{d.filename}</span>
                      {inScope && <span className="shrink-0 font-semibold text-scope-700">✓</span>}
                    </button>
                  )
                })}
            </div>
          )}
        </div>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
          }}
          disabled={streaming}
          rows={2}
          placeholder={
            streaming
              ? 'Waiting for the answer to finish…'
              : 'Ask about Singapore law, e.g. “What notice must my employer give to terminate me?”'
          }
          className="input-base max-h-40 min-h-[3rem] flex-1 resize-y py-2 leading-6 disabled:bg-paper-100 disabled:text-paper-500"
          aria-label="Your question"
        />

        {streaming ? (
          <button type="button" onClick={onStop} className="btn-danger-quiet py-2.5">
            <span className="inline-block h-2.5 w-2.5 rounded-[2px] bg-danger-700" aria-hidden="true" />
            Stop
          </button>
        ) : (
          <button type="button" onClick={submit} disabled={!text.trim()} className="btn-primary py-2.5">
            Send
          </button>
        )}
      </div>
      <p className="mx-auto mt-1.5 max-w-3xl text-[11px] text-paper-500">
        Enter to send · Shift+Enter for a new line. Answers cite the provisions and judgments they
        rely on — click a citation to read the source.
      </p>
    </div>
  )
}
