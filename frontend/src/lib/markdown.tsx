import { Fragment } from 'react'
import type { ReactNode } from 'react'

/**
 * Minimal, dependency-free markdown block renderer for assistant answers.
 *
 * Supports: headings, paragraphs, unordered/ordered lists (one nesting level
 * via indentation), tables, fenced code blocks, blockquotes and horizontal
 * rules. All inline text — including table cells and list items — is passed
 * through the caller-supplied `renderInline`, which is where `[CITE:n]`
 * markers become citation chips. Everything is emitted as React elements;
 * no HTML string is ever injected, so LLM output cannot smuggle markup.
 */
export type InlineRenderer = (text: string, keyPrefix: string) => ReactNode

const HEADING = /^(#{1,6})\s+(.*)$/
const HR = /^ {0,3}(?:-{3,}|\*{3,}|_{3,})\s*$/
const UL_ITEM = /^(\s*)[-*+]\s+(.*)$/
const OL_ITEM = /^(\s*)\d+[.)]\s+(.*)$/
const TABLE_SEPARATOR = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/
const FENCE = /^\s*(```|~~~)\s*(\S*)\s*$/
const BLOCKQUOTE = /^\s*>\s?(.*)$/

interface ListItem {
  text: string
  children: ListItem[]
}

function parseListItems(
  lines: string[],
  start: number,
  matcher: RegExp,
): { items: ListItem[]; end: number } {
  const items: ListItem[] = []
  let i = start
  let baseIndent: number | null = null
  while (i < lines.length) {
    const m = matcher.exec(lines[i] ?? '')
    if (!m) break
    const indent = (m[1] ?? '').length
    const body = m[2] ?? ''
    if (baseIndent === null) baseIndent = indent
    const lastItem = items[items.length - 1]
    if (indent > baseIndent && lastItem) {
      // Nested item — attach to the previous top-level item (single level).
      lastItem.children.push({ text: body, children: [] })
    } else if (indent < baseIndent) {
      break
    } else {
      items.push({ text: body, children: [] })
    }
    i++
  }
  return { items, end: i }
}

function splitTableRow(line: string): string[] {
  let row = line.trim()
  if (row.startsWith('|')) row = row.slice(1)
  if (row.endsWith('|')) row = row.slice(0, -1)
  // Split on unescaped pipes.
  return row.split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, '|'))
}

export function renderMarkdown(text: string, renderInline: InlineRenderer): ReactNode[] {
  const lines = text.split('\n')
  const blocks: ReactNode[] = []
  let key = 0
  let i = 0

  const paragraphBuffer: string[] = []
  const flushParagraph = () => {
    if (paragraphBuffer.length === 0) return
    const para = paragraphBuffer.join('\n')
    paragraphBuffer.length = 0
    blocks.push(
      <p key={key++} className="whitespace-pre-wrap">
        {renderInline(para, `p${key}`)}
      </p>,
    )
  }

  while (i < lines.length) {
    const line = lines[i] ?? ''

    // Fenced code block.
    const fence = FENCE.exec(line)
    if (fence) {
      flushParagraph()
      const marker = fence[1] ?? '```'
      const codeLines: string[] = []
      i++
      while (i < lines.length && !(lines[i] ?? '').trim().startsWith(marker)) {
        codeLines.push(lines[i] ?? '')
        i++
      }
      if (i < lines.length) i++ // consume closing fence
      blocks.push(
        <pre
          key={key++}
          className="overflow-x-auto rounded-md border border-paper-200 bg-paper-100 px-3 py-2.5 font-mono text-[13px] leading-6 text-ink-900"
        >
          <code>{codeLines.join('\n')}</code>
        </pre>,
      )
      continue
    }

    // Blank line ends the current paragraph.
    if (line.trim() === '') {
      flushParagraph()
      i++
      continue
    }

    // Horizontal rule.
    if (HR.test(line)) {
      flushParagraph()
      blocks.push(<hr key={key++} className="my-1 border-paper-200" />)
      i++
      continue
    }

    // Heading.
    const heading = HEADING.exec(line)
    if (heading) {
      flushParagraph()
      const level = (heading[1] ?? '#').length
      const content = renderInline(heading[2] ?? '', `h${key}`)
      if (level === 1) {
        blocks.push(
          <h3 key={key++} className="font-sans text-[17px] leading-6 font-semibold text-ink-950">
            {content}
          </h3>,
        )
      } else if (level === 2) {
        blocks.push(
          <h4 key={key++} className="font-sans text-base leading-6 font-semibold text-ink-950">
            {content}
          </h4>,
        )
      } else {
        blocks.push(
          <h5 key={key++} className="font-sans text-sm leading-5 font-semibold text-ink-900">
            {content}
          </h5>,
        )
      }
      i++
      continue
    }

    // Blockquote — collect consecutive quoted lines.
    if (BLOCKQUOTE.test(line)) {
      flushParagraph()
      const quoted: string[] = []
      while (i < lines.length) {
        const q = BLOCKQUOTE.exec(lines[i] ?? '')
        if (!q) break
        quoted.push(q[1] ?? '')
        i++
      }
      blocks.push(
        <blockquote
          key={key++}
          className="border-l-2 border-paper-300 pl-3 whitespace-pre-wrap text-ink-800 italic"
        >
          {renderInline(quoted.join('\n'), `q${key}`)}
        </blockquote>,
      )
      continue
    }

    // Table: a pipe row followed by a separator row.
    const nextLine = lines[i + 1]
    if (line.includes('|') && nextLine !== undefined && TABLE_SEPARATOR.test(nextLine)) {
      flushParagraph()
      const headers = splitTableRow(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length) {
        const rowLine = lines[i] ?? ''
        if (!rowLine.includes('|') || rowLine.trim() === '') break
        rows.push(splitTableRow(rowLine))
        i++
      }
      blocks.push(
        <div key={key++} className="overflow-x-auto">
          <table className="w-full border-collapse text-left font-sans text-[13px] leading-5">
            <thead>
              <tr className="border-b border-paper-300">
                {headers.map((h, hi) => (
                  <th key={hi} className="py-1.5 pr-3 font-semibold text-ink-900">
                    {renderInline(h, `th${key}-${hi}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri} className="border-b border-paper-200 text-ink-800">
                  {r.map((c, ci) => (
                    <td key={ci} className="py-1.5 pr-3 align-top">
                      {renderInline(c, `td${key}-${ri}-${ci}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    // Lists.
    const ulMatch = UL_ITEM.exec(line)
    const olMatch = OL_ITEM.exec(line)
    if (ulMatch || olMatch) {
      flushParagraph()
      const matcher = ulMatch ? UL_ITEM : OL_ITEM
      const { items, end } = parseListItems(lines, i, matcher)
      i = end
      const ListTag = ulMatch ? 'ul' : 'ol'
      blocks.push(
        <ListTag
          key={key++}
          className={`space-y-1 pl-5 ${ulMatch ? 'list-disc' : 'list-decimal'} marker:text-paper-500`}
        >
          {items.map((item, ii) => (
            <li key={ii}>
              {renderInline(item.text, `li${key}-${ii}`)}
              {item.children.length > 0 && (
                <ul className="mt-1 list-[circle] space-y-1 pl-5 marker:text-paper-400">
                  {item.children.map((child, ci) => (
                    <li key={ci}>{renderInline(child.text, `li${key}-${ii}-${ci}`)}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ListTag>,
      )
      continue
    }

    // Plain text — accumulate into the current paragraph.
    paragraphBuffer.push(line)
    i++
  }

  flushParagraph()
  return blocks.map((b, bi) => <Fragment key={bi}>{b}</Fragment>)
}
