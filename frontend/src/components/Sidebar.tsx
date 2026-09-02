import { useCallback, useEffect, useState } from 'react'
import { Link, NavLink, useNavigate, useSearchParams } from 'react-router-dom'
import {
  adminSync,
  deleteConversation,
  getHealth,
  listConversations,
  renameConversation,
} from '../api'
import type { ConversationSummary, HealthResponse } from '../api'
import { useApp } from '../context/AppContext'
import { useToast } from '../context/ToastContext'
import { formatDateTime } from '../lib/format'
import { Wordmark } from './Wordmark'

const NAV_ITEMS = [
  { to: '/chat', label: 'Chat' },
  { to: '/explorer', label: 'Explorer' },
  { to: '/documents', label: 'Documents' },
]

interface SidebarProps {
  /** Below md the sidebar renders as a drawer; this controls its visibility. */
  mobileOpen: boolean
  onMobileClose: () => void
}

interface ConversationGroup {
  label: string
  items: ConversationSummary[]
}

/** Group conversations by recency: Today / Previous 7 days / Older. */
function groupByDate(conversations: ConversationSummary[]): ConversationGroup[] {
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const weekAgo = startOfToday - 7 * 24 * 60 * 60 * 1000
  const today: ConversationGroup = { label: 'Today', items: [] }
  const week: ConversationGroup = { label: 'Previous 7 days', items: [] }
  const older: ConversationGroup = { label: 'Older', items: [] }
  for (const c of conversations) {
    const t = new Date(c.updated_at).getTime()
    if (Number.isNaN(t) || t >= startOfToday) today.items.push(c)
    else if (t >= weekAgo) week.items.push(c)
    else older.items.push(c)
  }
  return [today, week, older].filter((g) => g.items.length > 0)
}

export function Sidebar({ mobileOpen, onMobileClose }: SidebarProps) {
  const { conversationsVersion, bumpConversations } = useApp()
  const toast = useToast()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const activeId = searchParams.get('c')

  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [filter, setFilter] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthError, setHealthError] = useState(false)
  const [syncing, setSyncing] = useState(false)

  const refetchConversations = useCallback(() => {
    listConversations()
      .then(setConversations)
      .catch((e: unknown) => {
        toast.push(e instanceof Error ? e.message : 'Failed to load conversations.')
      })
  }, [toast])

  useEffect(() => {
    refetchConversations()
  }, [refetchConversations, conversationsVersion])

  useEffect(() => {
    let cancelled = false
    const load = () => {
      getHealth()
        .then((h) => {
          if (cancelled) return
          setHealth(h)
          setHealthError(false)
        })
        .catch(() => {
          if (!cancelled) setHealthError(true)
        })
    }
    load()
    const timer = window.setInterval(load, 60_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const go = (path: string) => {
    navigate(path)
    onMobileClose()
  }

  const startRename = (c: ConversationSummary) => {
    setConfirmingId(null)
    setEditingId(c.id)
    setEditTitle(c.title)
  }

  const commitRename = async () => {
    if (!editingId) return
    const id = editingId
    const title = editTitle.trim()
    setEditingId(null)
    if (!title) return
    try {
      await renameConversation(id, title)
      bumpConversations()
    } catch (e) {
      toast.push(e instanceof Error ? e.message : 'Rename failed.')
    }
  }

  const confirmDelete = async (c: ConversationSummary) => {
    setConfirmingId(null)
    try {
      await deleteConversation(c.id)
      if (activeId === c.id) go('/chat')
      bumpConversations()
    } catch (e) {
      toast.push(e instanceof Error ? e.message : 'Delete failed.')
    }
  }

  const runSync = async () => {
    setSyncing(true)
    try {
      const res = await adminSync(false)
      toast.push(res.reason, res.started ? 'success' : 'info')
    } catch (e) {
      toast.push(e instanceof Error ? e.message : 'Sync request failed.')
    } finally {
      setSyncing(false)
    }
  }

  const visible = conversations.filter((c) =>
    c.title.toLowerCase().includes(filter.trim().toLowerCase()),
  )
  const groups = groupByDate(visible)

  const dotColor = healthError
    ? 'bg-danger-500'
    : health?.status === 'ok'
      ? 'bg-positive-500'
      : health
        ? 'bg-caution-500'
        : 'bg-paper-300'

  return (
    <>
      {/* Mobile scrim */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-ink-950/40 md:hidden"
          onClick={onMobileClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`z-50 w-72 shrink-0 flex-col border-r border-paper-200 bg-paper-100 ${
          mobileOpen ? 'fixed inset-y-0 left-0 flex shadow-panel' : 'hidden'
        } md:static md:flex md:shadow-none`}
        aria-label="App navigation"
      >
        <div className="flex items-center gap-2.5 border-b border-paper-200 px-4 py-3">
          <Link
            to="/"
            onClick={onMobileClose}
            className="flex min-w-0 items-center gap-2.5"
            title="About SG Law Assistant"
          >
            <Wordmark className="h-8 w-8" />
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold tracking-tight text-ink-950">
                SG Law Assistant
              </span>
              <span className="block text-[11px] leading-4 text-paper-600">
                Cited Singapore legal information
              </span>
            </span>
          </Link>
          <button
            type="button"
            onClick={onMobileClose}
            aria-label="Close navigation"
            className="ml-auto rounded-md p-1.5 text-paper-600 hover:bg-paper-200 hover:text-ink-900 md:hidden"
          >
            <svg viewBox="0 0 16 16" className="h-4 w-4 fill-current" aria-hidden="true">
              <path d="m4.1 3 3.9 3.9L11.9 3 13 4.1 9.1 8l3.9 3.9-1.1 1.1L8 9.1 4.1 13 3 11.9 6.9 8 3 4.1 4.1 3Z" />
            </svg>
          </button>
        </div>

        <nav className="flex gap-1 border-b border-paper-200 px-2 py-2" aria-label="Main">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={onMobileClose}
              className={({ isActive }) =>
                `flex-1 rounded-md px-2 py-1.5 text-center text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-ink-900 text-white'
                    : 'text-ink-800 hover:bg-paper-200 hover:text-ink-950'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-2 px-3 pt-3 pb-2">
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search conversations"
            className="input-base min-w-0 flex-1"
            aria-label="Search conversations"
          />
          <button
            type="button"
            onClick={() => go('/chat')}
            title="New conversation"
            className="shrink-0 rounded-md border border-paper-300 bg-white px-2.5 py-1.5 text-sm font-semibold text-ink-800 transition-colors hover:border-ink-300 hover:bg-ink-50"
          >
            + New
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          {visible.length === 0 && (
            <p className="px-2 py-4 text-center text-xs text-paper-500">
              {conversations.length === 0 ? 'No conversations yet.' : 'No matches.'}
            </p>
          )}
          {groups.map((group) => (
            <section key={group.label} className="mb-1">
              <h2 className="px-2 pt-2 pb-1 text-[10px] font-semibold tracking-[0.08em] text-paper-500 uppercase">
                {group.label}
              </h2>
              <ul className="space-y-0.5">
                {group.items.map((c) => (
                  <li key={c.id} className="group relative">
                    {editingId === c.id ? (
                      <input
                        autoFocus
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onBlur={() => void commitRename()}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void commitRename()
                          if (e.key === 'Escape') setEditingId(null)
                        }}
                        className="input-base w-full border-ink-400"
                        aria-label="Conversation title"
                      />
                    ) : confirmingId === c.id ? (
                      <div className="flex items-center gap-1.5 rounded-md border border-danger-200 bg-danger-50 px-2 py-1.5">
                        <span className="min-w-0 flex-1 truncate text-xs font-medium text-danger-900">
                          Delete “{c.title || 'Untitled'}”?
                        </span>
                        <button
                          type="button"
                          onClick={() => void confirmDelete(c)}
                          className="shrink-0 rounded-sm bg-danger-700 px-2 py-0.5 text-[11px] font-semibold text-white hover:bg-danger-800"
                        >
                          Delete
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmingId(null)}
                          className="shrink-0 rounded-sm border border-paper-300 bg-white px-2 py-0.5 text-[11px] font-medium text-ink-800 hover:bg-paper-100"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => go(`/chat?c=${encodeURIComponent(c.id)}`)}
                        className={`w-full rounded-md px-2 py-1.5 pr-14 text-left text-sm transition-colors ${
                          activeId === c.id
                            ? 'bg-ink-100 font-medium text-ink-950'
                            : 'text-ink-800 hover:bg-paper-200'
                        }`}
                      >
                        <span className="block truncate">{c.title || 'Untitled'}</span>
                        <span className="block truncate text-[11px] text-paper-500">
                          {c.message_count} messages · {formatDateTime(c.updated_at)}
                        </span>
                      </button>
                    )}
                    {editingId !== c.id && confirmingId !== c.id && (
                      <span className="absolute top-1.5 right-1.5 hidden gap-0.5 group-hover:flex group-focus-within:flex">
                        <button
                          type="button"
                          onClick={() => startRename(c)}
                          title="Rename"
                          aria-label={`Rename ${c.title || 'conversation'}`}
                          className="rounded-sm bg-white/90 p-1 text-paper-600 shadow-card hover:text-ink-900"
                        >
                          <svg
                            viewBox="0 0 16 16"
                            className="h-3.5 w-3.5 fill-current"
                            aria-hidden="true"
                          >
                            <path d="M11.9 1.6 14.4 4 5.8 12.7l-3.2.7.7-3.2 8.6-8.6Zm-1 2.1L4.6 10l1.4 1.4 6.3-6.3-1.4-1.4Z" />
                          </svg>
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmingId(c.id)}
                          title="Delete"
                          aria-label={`Delete ${c.title || 'conversation'}`}
                          className="rounded-sm bg-white/90 p-1 text-paper-600 shadow-card hover:text-danger-700"
                        >
                          <svg
                            viewBox="0 0 16 16"
                            className="h-3.5 w-3.5 fill-current"
                            aria-hidden="true"
                          >
                            <path d="M6 2h4v1.5h4V5H2V3.5h4V2ZM3.5 6h9l-.7 8.1a1 1 0 0 1-1 .9H5.2a1 1 0 0 1-1-.9L3.5 6Z" />
                          </svg>
                        </button>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>

        <footer className="border-t border-paper-200 px-4 py-3">
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${dotColor}`}
              title={
                healthError
                  ? 'Backend unreachable'
                  : health
                    ? `Status: ${health.status} · embedder ${health.models.embedder} · sg_law ${health.qdrant.sg_law} chunks`
                    : 'Checking…'
              }
            />
            <div className="min-w-0 flex-1 text-[11px] leading-4 text-paper-600">
              {healthError ? (
                <span className="text-danger-700">Backend unreachable</span>
              ) : (
                <>
                  Corpus last synced{' '}
                  <span className="text-ink-800">
                    {health?.last_sync ? formatDateTime(health.last_sync) : 'never'}
                  </span>
                </>
              )}
            </div>
            <button
              type="button"
              onClick={() => void runSync()}
              disabled={syncing || healthError}
              title="Request a corpus sync (only runs 05:00–07:00 SGT)"
              className="shrink-0 rounded-sm border border-paper-300 bg-white px-1.5 py-0.5 text-[11px] font-medium text-ink-700 transition-colors hover:bg-paper-100 disabled:opacity-50"
            >
              {syncing ? 'Syncing…' : 'Sync'}
            </button>
          </div>
        </footer>
      </aside>
    </>
  )
}
