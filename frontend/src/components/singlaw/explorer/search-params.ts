/**
 * URL search-param validators for the explorer routes. Kept out of the route
 * files so they only export components (fast refresh) and can be unit tested.
 */
import { isDocTypeFilter, type DocTypeFilter } from "./helpers";

/** All keys optional so a plain `<Link to="/sources">` elsewhere stays valid. */
export interface SourcesSearch {
  mode?: "search";
  q?: string;
  type?: Exclude<DocTypeFilter, "all">;
}

export function validateSourcesSearch(raw: Record<string, unknown>): SourcesSearch {
  const out: SourcesSearch = {};
  if (raw["mode"] === "search") out.mode = "search";
  const q = raw["q"];
  if (typeof q === "string" && q.trim()) out.q = q.trim();
  const type = raw["type"];
  if (isDocTypeFilter(type) && type !== "all") out.type = type;
  return out;
}

export interface DocSearch {
  chunk?: string;
}

export function validateDocSearch(raw: Record<string, unknown>): DocSearch {
  const chunk = raw["chunk"];
  return typeof chunk === "string" && chunk ? { chunk } : {};
}
