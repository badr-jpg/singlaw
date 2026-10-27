import { useEffect, useMemo, useState } from "react";
import { ChevronRight, Search } from "lucide-react";
import type { DocTreeNode } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { ancestorKeys, flattenLeaves, nodeKey } from "./helpers";

function leafCount(node: DocTreeNode): number {
  if (!node.children.length) return node.chunk_id ? 1 : 0;
  return node.children.reduce((n, child) => n + leafCount(child), 0);
}

/**
 * Collapsible outline of a document: Parts → Divisions → Section leaves for
 * legislation; court → paragraph ranges for judgments. Ancestors of the
 * selected leaf open automatically; a filter box flattens matching leaves.
 */
export function DocOutline({
  tree,
  selected,
  onSelect,
}: {
  tree: DocTreeNode[];
  selected: string | null;
  onSelect: (chunkId: string) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const initial = new Set<string>(selected ? ancestorKeys(tree, selected) : []);
    if (!initial.size && tree[0]?.children.length) initial.add(nodeKey([0]));
    return initial;
  });
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!selected) return;
    const keys = ancestorKeys(tree, selected);
    if (!keys.length) return;
    setExpanded((prev) => {
      if (keys.every((k) => prev.has(k))) return prev;
      const next = new Set(prev);
      keys.forEach((k) => next.add(k));
      return next;
    });
  }, [tree, selected]);

  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const leaves = useMemo(() => flattenLeaves(tree), [tree]);
  const query = filter.trim().toLowerCase();
  const matches = query
    ? leaves.filter(
        (n) =>
          n.label.toLowerCase().includes(query) || (n.citation ?? "").toLowerCase().includes(query),
      )
    : null;

  const renderNodes = (nodes: DocTreeNode[], path: number[]) => (
    <ul>
      {nodes.map((node, i) => {
        const here = [...path, i];
        const key = nodeKey(here);
        if (node.children.length) {
          const open = expanded.has(key);
          return (
            <li key={key}>
              <button
                type="button"
                className="xp-outline-toggle"
                aria-expanded={open}
                onClick={() => toggle(key)}
              >
                <ChevronRight aria-hidden="true" />
                <span>{node.label}</span>
                <small>{leafCount(node)}</small>
              </button>
              {open && renderNodes(node.children, here)}
            </li>
          );
        }
        if (node.chunk_id) {
          const id = node.chunk_id;
          return (
            <li key={key}>
              <button
                type="button"
                className="xp-outline-leaf"
                aria-current={selected === id ? "true" : undefined}
                onClick={() => onSelect(id)}
              >
                {node.label}
              </button>
            </li>
          );
        }
        return (
          <li key={key}>
            <span className="xp-outline-plain">{node.label}</span>
          </li>
        );
      })}
    </ul>
  );

  return (
    <nav aria-label="Document outline">
      <div className="xp-outline-heading">
        <span className="eyebrow">Outline</span>
        <span>
          {leaves.length} {leaves.length === 1 ? "provision" : "provisions"}
        </span>
      </div>
      {leaves.length > 8 && (
        <div className="xp-outline-filter">
          <Search aria-hidden="true" />
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter sections…"
            aria-label="Filter the outline"
          />
        </div>
      )}
      {matches ? (
        matches.length ? (
          <ul>
            {matches.map((node) => {
              const id = node.chunk_id!;
              return (
                <li key={id}>
                  <button
                    type="button"
                    className="xp-outline-leaf"
                    aria-current={selected === id ? "true" : undefined}
                    onClick={() => onSelect(id)}
                  >
                    {node.label}
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="xp-outline-plain">No sections match “{filter.trim()}”.</p>
        )
      ) : (
        renderNodes(tree, [])
      )}
    </nav>
  );
}
