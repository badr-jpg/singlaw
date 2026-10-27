import { createContext } from "react";
import type { Source } from "@/lib/api";

/** Enough to open the source drawer; the full chunk is fetched there. */
export type SourceRef = Pick<Source, "chunk_id" | "citation"> & Partial<Source>;

export interface AnswerContextValue {
  sources: Source[];
  invalidCites: number[];
  openSource: (source: SourceRef) => void;
}

/**
 * Citation chips read their sources through context rather than a closure:
 * the markdown renderer is memoised on its text, so a closure captured before
 * the `sources` event arrived would otherwise go stale.
 */
export const AnswerContext = createContext<AnswerContextValue>({
  sources: [],
  invalidCites: [],
  openSource: () => {},
});
