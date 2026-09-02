import { useApp } from '../context/AppContext'

/**
 * Persistent, non-dismissible disclaimer shown at the bottom of every route.
 */
export function DisclaimerBar() {
  const { disclaimer } = useApp()
  return (
    <footer className="z-40 shrink-0 border-t border-paper-300 bg-paper-100 px-4 py-1.5">
      <p className="text-center text-xs text-ink-800">
        <svg
          viewBox="0 0 16 16"
          className="mr-1.5 inline-block h-3.5 w-3.5 fill-paper-500 align-[-2px]"
          aria-hidden="true"
        >
          <path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0Zm.75 12h-1.5V7h1.5v5Zm0-7h-1.5V4h1.5v1Z" />
        </svg>
        {disclaimer}
      </p>
    </footer>
  )
}
