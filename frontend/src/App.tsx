import { useCallback, useState } from 'react'
import { BrowserRouter, Link, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { DisclaimerBar } from './components/DisclaimerBar'
import { Sidebar } from './components/Sidebar'
import { SourcePanel } from './components/SourcePanel'
import { Wordmark } from './components/Wordmark'
import { AppProvider } from './context/AppContext'
import { ToastProvider } from './context/ToastContext'
import { ChatPage } from './pages/ChatPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { ExplorerPage } from './pages/ExplorerPage'
import { LandingPage } from './pages/LandingPage'

/**
 * Root layout: every route — landing included — carries the persistent,
 * non-dismissible legal-information disclaimer and the source slide-over.
 */
function RootLayout() {
  return (
    <div className="flex h-screen flex-col bg-paper-50 text-ink-950">
      <div className="flex min-h-0 flex-1 flex-col">
        <Outlet />
      </div>
      <DisclaimerBar />
      <SourcePanel />
    </div>
  )
}

const PAGE_NAMES: Record<string, string> = {
  '/chat': 'Chat',
  '/explorer': 'Explorer',
  '/documents': 'Documents',
}

/** App chrome: sidebar on desktop, hamburger drawer below 768px. */
function Shell() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()
  const closeSidebar = useCallback(() => setSidebarOpen(false), [])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Mobile top bar */}
      <header className="flex shrink-0 items-center gap-2 border-b border-paper-200 bg-paper-25 px-3 py-2 md:hidden">
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          aria-label="Open navigation"
          className="rounded-md border border-paper-300 bg-white p-2 text-ink-700 hover:bg-ink-50"
        >
          <svg viewBox="0 0 16 16" className="h-4 w-4 fill-current" aria-hidden="true">
            <path d="M2 3.5h12V5H2V3.5Zm0 3.75h12v1.5H2v-1.5ZM2 11h12v1.5H2V11Z" />
          </svg>
        </button>
        <Link to="/" className="flex items-center gap-2" aria-label="SG Law Assistant home">
          <Wordmark className="h-6 w-6" />
          <span className="text-sm font-semibold tracking-tight text-ink-950">SG Law Assistant</span>
        </Link>
        <span className="ml-auto text-xs font-medium text-paper-600">
          {PAGE_NAMES[location.pathname] ?? ''}
        </span>
      </header>

      <div className="flex min-h-0 flex-1">
        <Sidebar mobileOpen={sidebarOpen} onMobileClose={closeSidebar} />
        <main className="flex min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppProvider>
          <Routes>
            <Route element={<RootLayout />}>
              <Route path="/" element={<LandingPage />} />
              <Route element={<Shell />}>
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/explorer" element={<ExplorerPage />} />
                <Route path="/documents" element={<DocumentsPage />} />
              </Route>
            </Route>
          </Routes>
        </AppProvider>
      </ToastProvider>
    </BrowserRouter>
  )
}
