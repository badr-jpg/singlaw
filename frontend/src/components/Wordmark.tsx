/**
 * The scales-of-justice mark used in the favicon, sidebar and landing nav.
 * Rendered inline so it always matches the current palette.
 */
export function Wordmark({ className = 'h-8 w-8' }: { className?: string }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-md bg-ink-900 ${className}`}
      aria-hidden="true"
    >
      <svg viewBox="0 0 32 32" className="h-[70%] w-[70%]">
        <g stroke="#faf9f6" strokeWidth="1.8" fill="none" strokeLinecap="round">
          <line x1="16" y1="6" x2="16" y2="24" />
          <line x1="7" y1="10" x2="25" y2="10" />
          <path d="M4 18 L7 10 L10 18 A3 3 0 0 1 4 18 Z" />
          <path d="M22 18 L25 10 L28 18 A3 3 0 0 1 22 18 Z" />
          <line x1="11" y1="26" x2="21" y2="26" />
        </g>
      </svg>
    </span>
  )
}
