import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { deleteDocument, listDocuments, uploadDocument } from '../api'
import type { UploadedDocument } from '../api'
import { useToast } from '../context/ToastContext'
import { usePageTitle } from '../hooks/usePageTitle'
import { formatDateTime, statusLabel } from '../lib/format'

export function DocumentsPage() {
  usePageTitle('Documents · SG Law Assistant')
  const toast = useToast()
  const navigate = useNavigate()
  const [docs, setDocs] = useState<UploadedDocument[] | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(0)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const refetch = useCallback(() => {
    listDocuments()
      .then(setDocs)
      .catch((e: unknown) => {
        toast.push(e instanceof Error ? e.message : 'Failed to load documents.')
      })
  }, [toast])

  useEffect(() => {
    refetch()
  }, [refetch])

  // Poll every 2s while any document is still being processed.
  const hasInFlight =
    docs?.some((d) => d.status === 'pending' || d.status === 'processing') ?? false
  useEffect(() => {
    if (!hasInFlight) return
    const timer = window.setInterval(refetch, 2000)
    return () => window.clearInterval(timer)
  }, [hasInFlight, refetch])

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files)
      if (list.length === 0) return
      setUploading((n) => n + list.length)
      await Promise.all(
        list.map(async (file) => {
          try {
            await uploadDocument(file)
          } catch (e) {
            toast.push(
              `${file.name}: ${e instanceof Error ? e.message : 'upload failed.'}`,
              'error',
            )
          } finally {
            setUploading((n) => n - 1)
          }
        }),
      )
      refetch()
    },
    [refetch, toast],
  )

  const remove = async (doc: UploadedDocument) => {
    if (!window.confirm(`Delete “${doc.filename}” and its indexed content?`)) return
    try {
      await deleteDocument(doc.id)
      refetch()
    } catch (e) {
      toast.push(e instanceof Error ? e.message : 'Delete failed.')
    }
  }

  return (
    <div className="min-w-0 flex-1 overflow-y-auto bg-paper-50">
      <div className="mx-auto max-w-3xl px-5 py-6 sm:px-6">
        <h2 className="font-serif text-xl font-semibold text-ink-950">Your documents</h2>
        <p className="mt-1 text-sm leading-6 text-paper-700">
          Upload contracts, letters, or notices to ask questions about your own situation. Your
          documents describe your facts —{' '}
          <span className="font-medium text-ink-900">they are never treated as legal authority</span>
          , and they stay on this machine.
        </p>

        <div
          role="button"
          tabIndex={0}
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click()
          }}
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragOver(false)
            void handleFiles(e.dataTransfer.files)
          }}
          aria-label="Upload documents"
          className={`mt-4 flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors ${
            dragOver
              ? 'border-ink-500 bg-ink-50'
              : 'border-paper-300 bg-white hover:border-ink-300 hover:bg-ink-50/40'
          }`}
        >
          <svg viewBox="0 0 24 24" className="mb-2 h-8 w-8 fill-paper-400" aria-hidden="true">
            <path d="M12 3 6.5 8.5l1.4 1.4L11 6.8V16h2V6.8l3.1 3.1 1.4-1.4L12 3ZM5 18v3h14v-3h-2v1H7v-1H5Z" />
          </svg>
          <p className="text-sm font-medium text-ink-800">
            {dragOver ? 'Drop to upload' : 'Drag and drop files here, or click to choose'}
          </p>
          <p className="mt-1 text-xs text-paper-500">PDF, Word, or plain text</p>
          {uploading > 0 && (
            <p className="mt-2 text-xs font-medium text-ink-700">
              Uploading {uploading} file{uploading > 1 ? 's' : ''}…
            </p>
          )}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.doc,.txt,.md"
            className="hidden"
            onChange={(e) => {
              if (e.target.files) void handleFiles(e.target.files)
              e.target.value = ''
            }}
          />
        </div>

        <div className="mt-6">
          {docs === null && <p className="text-sm text-paper-600">Loading documents…</p>}
          {docs !== null && docs.length === 0 && (
            <p className="rounded-md border border-paper-200 bg-white px-4 py-6 text-center text-sm text-paper-500">
              Nothing uploaded yet.
            </p>
          )}
          {docs !== null && docs.length > 0 && (
            <ul className="divide-y divide-paper-100 rounded-md border border-paper-200 bg-white shadow-card">
              {docs.map((doc) => (
                <li key={doc.id} className="flex items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink-900">{doc.filename}</p>
                    <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-paper-600">
                      <DocStatus doc={doc} />
                      {doc.status === 'ready' && (
                        <span>
                          {doc.chunk_count} chunk{doc.chunk_count === 1 ? '' : 's'}
                        </span>
                      )}
                      <span>Added {formatDateTime(doc.created_at)}</span>
                    </p>
                    {doc.status === 'error' && doc.error && (
                      <p className="mt-1 rounded-sm border border-danger-200 bg-danger-50 px-2 py-1 text-xs text-danger-800">
                        {doc.error}
                      </p>
                    )}
                  </div>
                  {doc.status === 'ready' && (
                    <button
                      type="button"
                      onClick={() => navigate(`/chat?doc=${encodeURIComponent(doc.id)}`)}
                      className="shrink-0 rounded-md border border-ink-200 bg-ink-50 px-2.5 py-1.5 text-xs font-semibold text-ink-800 transition-colors hover:border-ink-300 hover:bg-ink-100"
                    >
                      Ask about this document
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void remove(doc)}
                    title="Delete document"
                    aria-label={`Delete ${doc.filename}`}
                    className="shrink-0 rounded-md border border-paper-200 bg-white p-1.5 text-paper-500 transition-colors hover:border-danger-300 hover:text-danger-700"
                  >
                    <svg viewBox="0 0 16 16" className="h-4 w-4 fill-current" aria-hidden="true">
                      <path d="M6 2h4v1.5h4V5H2V3.5h4V2ZM3.5 6h9l-.7 8.1a1 1 0 0 1-1 .9H5.2a1 1 0 0 1-1-.9L3.5 6Z" />
                    </svg>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

function DocStatus({ doc }: { doc: UploadedDocument }) {
  const busy = doc.status === 'pending' || doc.status === 'processing'
  const cls =
    doc.status === 'ready'
      ? 'border-positive-300 bg-positive-50 text-positive-800'
      : doc.status === 'error'
        ? 'border-danger-300 bg-danger-50 text-danger-800'
        : 'border-caution-300 bg-caution-50 text-caution-900'
  return (
    <span className={`meta-chip ${cls}`}>
      {busy && (
        <svg viewBox="0 0 16 16" className="h-3 w-3 animate-spin fill-current" aria-hidden="true">
          <path d="M8 1a7 7 0 1 0 7 7h-1.8A5.2 5.2 0 1 1 8 2.8V1Z" />
        </svg>
      )}
      {statusLabel(doc.status)}
    </span>
  )
}
