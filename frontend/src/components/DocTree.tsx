import { useState } from 'react'
import type { DocTreeNode } from '../api'

interface TreeProps {
  nodes: DocTreeNode[]
  selectedChunkId: string | null
  onSelect: (chunkId: string) => void
}

/**
 * Collapsible outline of a document's structure (Part → Division → Section).
 * Leaves with a chunk_id load that provision into the reading pane.
 */
export function DocTree({ nodes, selectedChunkId, onSelect }: TreeProps) {
  return (
    <ul className="space-y-0.5 text-[13px]">
      {nodes.map((node, i) => (
        <TreeNode
          key={`${node.citation || node.label}-${i}`}
          node={node}
          depth={0}
          selectedChunkId={selectedChunkId}
          onSelect={onSelect}
        />
      ))}
    </ul>
  )
}

function TreeNode({
  node,
  depth,
  selectedChunkId,
  onSelect,
}: {
  node: DocTreeNode
  depth: number
  selectedChunkId: string | null
  onSelect: (chunkId: string) => void
}) {
  const hasChildren = node.children.length > 0
  const [expanded, setExpanded] = useState(depth === 0)
  const isSelected = node.chunk_id !== null && node.chunk_id === selectedChunkId

  return (
    <li>
      <div
        className={`flex items-start gap-1 rounded-sm py-0.5 pr-1 ${
          isSelected ? 'bg-ink-100' : 'hover:bg-paper-200'
        }`}
        style={{ paddingLeft: `${depth * 12}px` }}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            aria-label={expanded ? `Collapse ${node.label}` : `Expand ${node.label}`}
            className="mt-1 shrink-0 text-paper-500 hover:text-ink-800"
          >
            <svg
              viewBox="0 0 16 16"
              className={`h-3 w-3 fill-current transition-transform ${expanded ? 'rotate-90' : ''}`}
              aria-hidden="true"
            >
              <path d="M6 3.5 11 8l-5 4.5v-9Z" />
            </svg>
          </button>
        ) : (
          <span className="mt-1 h-3 w-3 shrink-0" aria-hidden="true" />
        )}
        {node.chunk_id ? (
          <button
            type="button"
            onClick={() => onSelect(node.chunk_id as string)}
            className={`min-w-0 flex-1 text-left leading-5 ${
              isSelected ? 'font-medium text-ink-950' : 'text-ink-800 hover:text-ink-950'
            }`}
          >
            {node.label}
          </button>
        ) : (
          <span className="min-w-0 flex-1 leading-5 font-medium text-paper-600">{node.label}</span>
        )}
      </div>
      {hasChildren && expanded && (
        <ul className="space-y-0.5">
          {node.children.map((child, i) => (
            <TreeNode
              key={`${child.citation || child.label}-${i}`}
              node={child}
              depth={depth + 1}
              selectedChunkId={selectedChunkId}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
    </li>
  )
}
