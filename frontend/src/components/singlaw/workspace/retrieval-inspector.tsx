import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { api } from "@/lib/api";
import { filteredSummary } from "@/lib/singlaw";
import type { SourceRef } from "./answer-context";


const STAGE_LABELS: [string, string][] = [
  ["analysis", "Query analysis (LLM)"],
  ["rewrite_hyde_extra_wait", "Rewrites + HyDE (LLM) — extra wait beyond analysis"],
  ["retrieval_citation_shortcircuit", "Citation lookup"],
  ["retrieval_hybrid_search", "Dense + sparse search (Qdrant)"],
  ["retrieval_fusion_filters", "Fusion & in-force filters"],
  ["retrieval_rerank", "Cross-encoder rerank"],
  ["generation_first_token", "Answer — time to first token (LLM)"],
  ["generation", "Answer generation (LLM, total)"],
];

function humanizeStage(key: string): string {
  return key.replace(/^retrieval_/, "retrieval: ").replace(/_/g, " ");
}

/** Where the seconds went for this answer, from the server's `done` timings. */
export function AnswerTimings({ timings }: { timings: Record<string, number> }) {
  const total = timings["total"] ?? Object.values(timings).reduce((a, b) => Math.max(a, b), 0);
  const known = STAGE_LABELS.filter(([k]) => k in timings);
  const flags = Object.keys(timings).filter((k) => k.endsWith("_timed_out"));
  const extra = Object.keys(timings).filter(
    (k) => k !== "total" && !k.endsWith("_timed_out") && !STAGE_LABELS.some(([known]) => known === k),
  );
  const rows: [string, string][] = [...known, ...extra.map((k) => [k, humanizeStage(k)] as [string, string])];
  const fmt = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`);
  return (
    <section className="inspector-section" aria-label="Answer timing">
      <h4>
        Where the time went <span className="inspector-muted">· total {fmt(total)}</span>
      </h4>
      <ul className="timing-list">
        {rows.map(([key, label]) => {
          const ms = timings[key] ?? 0;
          const pct = total > 0 ? Math.max(1.5, Math.min(100, (ms / total) * 100)) : 0;
          const llm = /LLM/.test(label);
          return (
            <li key={key} className="timing-row">
              <span className="timing-label">{label}</span>
              <span className="timing-track" aria-hidden="true">
                <span className="timing-bar" data-llm={llm} style={{ width: `${pct}%` }} />
              </span>
              <span className="timing-value">{ms === 0 && llm ? "cached" : fmt(ms)}</span>
            </li>
          );
        })}
      </ul>
      {flags.length > 0 && (
        <p className="inspector-muted">
          {flags.includes("analysis_timed_out") &&
            "Query analysis missed the time budget — heuristic analysis was used. "}
          {flags.includes("rewrite_hyde_timed_out") &&
            "Rewrites/HyDE missed the time budget — retrieval ran on the raw question (results cached for next time)."}
        </p>
      )}
      <p className="inspector-muted">
        LLM stages are network round-trips to the language model (“cached” = reused from an
        earlier ask of the same question); retrieval stages run locally.
      </p>
    </section>
  );
}

/**
 * Collapsible "Show retrieval details" under each finished answer. Closed by
 * default; the first open re-runs retrieval with `include_debug` so a sceptical
 * reader can see what was rewritten, filtered and reranked.
 */
export function RetrievalInspector({
  question,
  docIds,
  businessId,
  answerTimings,
  openSource,
}: {
  question: string;
  docIds: string[] | null;
  businessId?: string | null | undefined;
  answerTimings?: Record<string, number> | undefined;
  openSource: (source: SourceRef) => void;
}) {
  const [open, setOpen] = useState(false);
  const [hydeOpen, setHydeOpen] = useState(false);
  const query = useQuery({
    queryKey: ["search-debug", question, docIds ?? null, businessId ?? null],
    queryFn: () =>
      api.search({
        query: question,
        include_debug: true,
        doc_ids: docIds,
        business_id: businessId ?? null,
      }),
    enabled: open,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
  const data = query.data;
  const filtered = data ? filteredSummary(data.filtered) : null;

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="inspector">
      <CollapsibleTrigger className="inspector-toggle">
        <ChevronRight aria-hidden="true" data-open={open || undefined} />
        {open ? "Hide retrieval details" : "Show retrieval details"}
      </CollapsibleTrigger>
      <CollapsibleContent className="inspector-body">
        {answerTimings && <AnswerTimings timings={answerTimings} />}
        {query.isPending && open && (
          <p className="inspector-muted">
            <Shimmer>Re-running retrieval with debugging on…</Shimmer>
          </p>
        )}
        {query.error && <p className="inspector-error">{query.error.message}</p>}
        {data && (
          <>
            {data.debug ? (
              <>
                <section>
                  <h4>Query rewrites</h4>
                  {data.debug.rewrites.length > 0 ? (
                    <ul>
                      {data.debug.rewrites.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="inspector-muted">No rewrites generated.</p>
                  )}
                </section>
                <section>
                  <h4>Hypothetical passage (HyDE)</h4>
                  {data.debug.hyde ? (
                    <>
                      <button
                        type="button"
                        className="inspector-link"
                        aria-expanded={hydeOpen}
                        onClick={() => setHydeOpen((v) => !v)}
                      >
                        {hydeOpen ? "Collapse passage" : "Expand passage"}
                      </button>
                      {hydeOpen && <p className="inspector-hyde">{data.debug.hyde}</p>}
                    </>
                  ) : (
                    <p className="inspector-muted">Not used for this question.</p>
                  )}
                </section>
                {data.debug.citation_shortcircuit.length > 0 && (
                  <section>
                    <h4>Citation short-circuits</h4>
                    <ul>
                      {data.debug.citation_shortcircuit.map((c, i) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </section>
                )}
                <section>
                  <h4>Filtering</h4>
                  <p>
                    {data.debug.candidates_pre_filter} candidates before status filters.{" "}
                    {filtered ? `${filtered}.` : "Nothing excluded."}
                  </p>
                </section>
                <section>
                  <h4>Candidates before rerank (RRF)</h4>
                  <div className="inspector-scroll">
                    <table className="inspector-table">
                      <thead>
                        <tr>
                          <th scope="col">Citation</th>
                          <th scope="col">RRF</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.debug.candidates_pre_rerank.map((c) => (
                          <tr key={c.chunk_id}>
                            <td>
                              <button
                                type="button"
                                className="inspector-link"
                                onClick={() =>
                                  openSource({ chunk_id: c.chunk_id, citation: c.citation })
                                }
                              >
                                {c.citation}
                              </button>
                            </td>
                            <td className="num">{c.rrf_score.toFixed(4)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              </>
            ) : (
              <p className="inspector-muted">The backend returned no debug information.</p>
            )}
            <section>
              <h4>Final results (cross-encoder + authority blend)</h4>
              <div className="inspector-scroll">
                <table className="inspector-table">
                  <thead>
                    <tr>
                      <th scope="col">Citation</th>
                      <th scope="col">CE</th>
                      <th scope="col">Authority</th>
                      <th scope="col">Final</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((r) => (
                      <tr key={r.chunk_id}>
                        <td>
                          <button
                            type="button"
                            className="inspector-link"
                            onClick={() => openSource(r)}
                          >
                            {r.citation}
                          </button>
                        </td>
                        <td className="num">{r.ce_score.toFixed(3)}</td>
                        <td className="num">{r.authority_score.toFixed(3)}</td>
                        <td className="num">{r.final_score.toFixed(3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            {data.debug && Object.keys(data.debug.timings_ms).length > 0 && (
              <p className="inspector-muted">
                Timings:{" "}
                {Object.entries(data.debug.timings_ms)
                  .map(([k, v]) => `${k} ${Math.round(v)} ms`)
                  .join(" · ")}
              </p>
            )}
          </>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
