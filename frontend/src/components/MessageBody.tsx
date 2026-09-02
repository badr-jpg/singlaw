import { Fragment, useCallback } from 'react'
import type { ReactNode } from 'react'
import type { Source } from '../api'
import { useApp } from '../context/AppContext'
import { renderMarkdown } from '../lib/markdown'

/**
 * Matches a trailing fragment that could still grow into a complete
 * `[CITE:n]` marker (e.g. "[", "[CIT", "[CITE:", "[CITE:12"). While tokens
 * are still streaming, such fragments are held back rather than rendered,
 * so a marker split across token boundaries never flashes as raw text.
 */
const PARTIAL_MARKER_AT_END = /\[(?:C(?:I(?:T(?:E(?::\d*)?)?)?)?)?$/

/**
 * Inline tokenizer: CITE markers, code spans, links, bold, italic.
 * CITE and code are matched first so their contents are never re-parsed.
 * A fresh instance is created per call because the renderer recurses.
 */
const INLINE_SOURCE =
  '\\[CITE:(\\d+)\\]|`([^`\\n]+)`|\\[([^\\]\\n]+)\\]\\((https?:\\/\\/[^\\s)]+)\\)|\\*\\*([^*\\n]+?)\\*\\*|__([^_\\n]+?)__|\\*([^*\\s][^*\\n]*?)\\*|_([^_\\s][^_\\n]*?)_'

/**
 * Sentinel appended to streaming text; rendered as the blinking caret.
 * Private-use codepoint — never occurs in genuine LLM output.
 */
const CARET_SENTINEL = '\uE000'

interface Props {
  content: string
  streaming: boolean
  sources: Source[]
  invalidCites?: number[]
}

/**
 * Assistant answer body: markdown blocks (headings, lists, tables, code)
 * rendered as React elements, with inline `[CITE:n]` markers rendered as
 * clickable legal-citation chips — never bare numbers, never raw HTML.
 * Clicking a chip opens the source slide-over for that chunk.
 */
export function MessageBody({ content, streaming, sources, invalidCites }: Props) {
  const { openSource } = useApp()

  let text = content
  if (streaming) {
    const partial = text.match(PARTIAL_MARKER_AT_END)
    if (partial && partial.index !== undefined) {
      text = text.slice(0, partial.index)
    }
    // The caret rides the very end of the streamed text, inside whatever
    // block the parser puts it in — like a real typing cursor.
    text += CARET_SENTINEL
  }

  const renderCite = useCallback(
    (n: number, key: string): ReactNode => {
      const source = sources.find((s) => s.n === n)
      const invalid = invalidCites?.includes(n) ?? false
      if (source) {
        return (
          <button
            key={key}
            type="button"
            onClick={() => openSource(source.chunk_id)}
            title={`${source.citation} — view source`}
            className={`mx-0.5 inline rounded-sm border px-1 py-px align-baseline font-sans text-[12px] leading-4 font-medium break-words whitespace-normal transition-colors ${
              invalid
                ? 'border-danger-300 bg-danger-50 text-danger-800 hover:bg-danger-100'
                : 'border-ink-200 bg-ink-50 text-ink-800 hover:border-ink-300 hover:bg-ink-100'
            }`}
          >
            {source.citation}
          </button>
        )
      }
      // Marker references a source the stream never delivered — flag it
      // rather than silently dropping or showing "[n]".
      return (
        <span
          key={key}
          title={`Citation ${n} could not be resolved to a source`}
          className="mx-0.5 inline rounded-sm border border-danger-300 bg-danger-50 px-1 py-px font-sans text-[12px] leading-4 font-medium text-danger-800"
        >
          unresolved citation
        </span>
      )
    },
    [sources, invalidCites, openSource],
  )

  const renderInline = useCallback(
    function renderInlineFn(input: string, keyPrefix: string): ReactNode {
      const nodes: ReactNode[] = []
      const re = new RegExp(INLINE_SOURCE, 'g')
      let last = 0
      let k = 0
      const pushText = (t: string) => {
        if (!t) return
        // Replace the caret sentinel with the blinking cursor element.
        const caretIdx = t.indexOf(CARET_SENTINEL)
        if (caretIdx === -1) {
          nodes.push(<Fragment key={`${keyPrefix}-t${k++}`}>{t}</Fragment>)
          return
        }
        const before = t.slice(0, caretIdx)
        const after = t.slice(caretIdx + 1).replaceAll(CARET_SENTINEL, '')
        if (before) nodes.push(<Fragment key={`${keyPrefix}-t${k++}`}>{before}</Fragment>)
        nodes.push(
          <span key={`${keyPrefix}-caret${k++}`} className="streaming-caret" aria-hidden="true" />,
        )
        if (after) nodes.push(<Fragment key={`${keyPrefix}-t${k++}`}>{after}</Fragment>)
      }

      for (let m = re.exec(input); m !== null; m = re.exec(input)) {
        if (m.index > last) pushText(input.slice(last, m.index))
        const [, cite, code, linkText, linkUrl, bold, bold2, em, em2] = m
        if (cite !== undefined) {
          nodes.push(renderCite(Number(cite), `${keyPrefix}-cite${k++}`))
        } else if (code !== undefined) {
          nodes.push(
            <code
              key={`${keyPrefix}-code${k++}`}
              className="rounded-sm border border-paper-200 bg-paper-100 px-1 py-px font-mono text-[0.85em] text-ink-900"
            >
              {code}
            </code>,
          )
        } else if (linkText !== undefined && linkUrl !== undefined) {
          nodes.push(
            <a
              key={`${keyPrefix}-a${k++}`}
              href={linkUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-ink-700 underline decoration-ink-300 underline-offset-2 hover:text-ink-950"
            >
              {renderInlineFn(linkText, `${keyPrefix}-a${k}`)}
            </a>,
          )
        } else if (bold !== undefined || bold2 !== undefined) {
          const inner = bold ?? bold2 ?? ''
          nodes.push(
            <strong key={`${keyPrefix}-b${k++}`} className="font-semibold">
              {renderInlineFn(inner, `${keyPrefix}-b${k}`)}
            </strong>,
          )
        } else if (em !== undefined || em2 !== undefined) {
          const inner = em ?? em2 ?? ''
          nodes.push(
            <em key={`${keyPrefix}-i${k++}`}>{renderInlineFn(inner, `${keyPrefix}-i${k}`)}</em>,
          )
        }
        last = m.index + m[0].length
      }
      if (last < input.length) pushText(input.slice(last))
      return <>{nodes}</>
    },
    [renderCite],
  )

  const blocks = renderMarkdown(text, renderInline)

  return <div className="space-y-3 font-serif text-[15px] leading-7 text-ink-950">{blocks}</div>
}
