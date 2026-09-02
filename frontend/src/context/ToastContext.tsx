import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

export type ToastKind = 'error' | 'info' | 'success'

interface Toast {
  id: number
  kind: ToastKind
  message: string
}

interface ToastApi {
  push: (message: string, kind?: ToastKind) => void
}

const ToastCtx = createContext<ToastApi | null>(null)

export function useToast(): ToastApi {
  const ctx = useContext(ToastCtx)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}

const KIND_STYLES: Record<ToastKind, string> = {
  error: 'border-danger-300 bg-danger-50 text-danger-900',
  info: 'border-paper-300 bg-white text-ink-900',
  success: 'border-positive-300 bg-positive-50 text-positive-900',
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((ts) => ts.filter((t) => t.id !== id))
  }, [])

  const push = useCallback(
    (message: string, kind: ToastKind = 'error') => {
      const id = nextId.current++
      setToasts((ts) => [...ts.slice(-4), { id, kind, message }])
      window.setTimeout(() => dismiss(id), 6000)
    },
    [dismiss],
  )

  const api = useMemo(() => ({ push }), [push])

  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-4 bottom-16 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            className={`pointer-events-auto flex items-start gap-2 rounded-md border px-3 py-2 text-sm shadow-pop ${KIND_STYLES[t.kind]}`}
          >
            <span className="flex-1">{t.message}</span>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              className="shrink-0 text-xs font-semibold opacity-60 hover:opacity-100"
              aria-label="Dismiss notification"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}
