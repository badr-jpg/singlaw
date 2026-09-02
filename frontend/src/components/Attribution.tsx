import { useApp } from '../context/AppContext'

/**
 * AGC attribution notice — required in small print wherever legislation text
 * is displayed. Uses backend-provided text when a chat meta has supplied it,
 * otherwise the fallback wording.
 */
export function Attribution({ text, className = '' }: { text?: string; className?: string }) {
  const { attribution } = useApp()
  return (
    <p className={`text-[11px] leading-4 text-paper-500 ${className}`}>{text || attribution}</p>
  )
}
