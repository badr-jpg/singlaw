import { useEffect, useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Search, SearchX, Sparkles, X } from "lucide-react";
import { toast } from "sonner";
import { api, type SearchResult } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ExplorerBadge, StatusBadge, TierBadge, TreatmentBadge } from "./badges";
import {
  docIdFromChunkId,
  formatCount,
  formatDate,
  formatScore,
  normaliseScore,
  scorePercent,
  showStatus,
} from "./helpers";
import { errorMessage } from "./errors";
import { CardSkeletons, ExplorerEmpty, ExplorerError } from "./states";

const EXAMPLES = [
  "notice period when I resign",
  "Employment Act 1968, s 14",
  "landlord keeping the security deposit",
  "what counts as personal data",
];

/**
 * "Search the law": runs the assistant's own retrieval (POST /api/search) and
 * lists ranked provisions with their relevance, authority and final scores.
 */
export function LawSearch({ query, onSubmit }: { query: string; onSubmit: (q: string) => void }) {
  const [draft, setDraft] = useState(query);
  useEffect(() => setDraft(query), [query]);

  const search = useQuery({
    queryKey: ["law-search", query],
    queryFn: () => api.search({ query, top_k: 20 }),
    enabled: query.trim().length > 0,
    staleTime: 60_000,
  });
  useEffect(() => {
    if (search.error) toast.error(errorMessage(search.error));
  }, [search.error]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = draft.trim();
    if (q) onSubmit(q);
  };

  return (
    <div>
      <form className="xp-search-form" onSubmit={submit} role="search" aria-label="Search the law">
        <div className="library-search">
          <Search aria-hidden="true" />
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask in plain words, or type a citation…"
            aria-label="Search query"
            className="pr-10"
            autoComplete="off"
          />
          {draft && (
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              className="absolute right-2 top-2"
              aria-label="Clear query"
              onClick={() => setDraft("")}
            >
              <X size={12} />
            </Button>
          )}
        </div>
        <Button type="submit" disabled={!draft.trim() || search.isFetching}>
          {search.isFetching ? "Searching…" : "Search"}
        </Button>
      </form>
      <p className="xp-search-hint">
        This is the retrieval step the assistant uses: hybrid search over the indexed corpus,
        re-ranked by relevance and authority. Repealed, spent and not-yet-commenced provisions are
        filtered out and counted, never silently served.
      </p>

      {!query.trim() ? (
        <ExplorerEmpty icon={Sparkles} title="Search the way the assistant does">
          <p>Try one of these, or ask your own question.</p>
          <div className="xp-examples">
            {EXAMPLES.map((ex) => (
              <Button key={ex} variant="outline" size="sm" onClick={() => onSubmit(ex)}>
                {ex}
              </Button>
            ))}
          </div>
        </ExplorerEmpty>
      ) : search.isPending ? (
        <CardSkeletons count={4} />
      ) : search.error ? (
        <ExplorerError
          title="Search didn't run"
          error={search.error}
          retry={() => search.refetch()}
        />
      ) : (
        <SearchResults data={search.data} query={query} />
      )}
    </div>
  );
}

function SearchResults({
  data,
  query,
}: {
  data: Awaited<ReturnType<typeof api.search>>;
  query: string;
}) {
  const f = data.filtered;
  const filteredTotal = f.repealed + f.spent + f.not_yet_commenced;
  return (
    <>
      <div className="xp-search-meta" role="status">
        <span>
          <strong>{formatCount(data.results.length)}</strong>{" "}
          {data.results.length === 1 ? "result" : "results"} for “{query}”
        </span>
        {data.intent && (
          <ExplorerBadge plain>Read as: {data.intent.replace(/_/g, " ")}</ExplorerBadge>
        )}
        <span>
          Filtered out: {f.repealed} repealed · {f.spent} spent · {f.not_yet_commenced} not yet
          commenced
          {filteredTotal === 0 ? " (none)" : ""}
        </span>
      </div>
      {data.low_confidence && (
        <p className="xp-low-confidence" role="status">
          <AlertTriangle size={15} aria-hidden="true" />
          <span>
            Low confidence: the assistant would say so before answering this.
            {data.low_confidence_reasons?.length ? (
              <ul>
                {data.low_confidence_reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            ) : null}
          </span>
        </p>
      )}
      {data.results.length === 0 ? (
        <ExplorerEmpty icon={SearchX} title="Nothing in the corpus matched">
          <p>
            Try the Act's name, a section number, or plainer words. Agency guidance (MOM, HDB,
            Customs, PDPC) is not indexed yet.
          </p>
        </ExplorerEmpty>
      ) : (
        <ol className="xp-results" aria-label="Search results">
          {data.results.map((r, i) => (
            <ResultCard key={r.chunk_id} result={r} rank={i + 1} />
          ))}
        </ol>
      )}
    </>
  );
}

function ResultCard({ result: r, rank }: { result: SearchResult; rank: number }) {
  const docId = docIdFromChunkId(r.chunk_id);
  const decided = formatDate(r.decision_date);
  return (
    <li className="xp-result">
      <div>
        <span className="xp-result-rank">
          #{rank}
          {r.pinned ? " · cited directly" : ""}
        </span>
        <h3>
          <Link to="/sources/$docId" params={{ docId }} search={{ chunk: r.chunk_id }}>
            {r.citation}
          </Link>
        </h3>
        {r.hierarchy_path.length > 0 && (
          <p className="xp-result-path">{r.hierarchy_path.join(" / ")}</p>
        )}
        <p className="xp-result-snippet">{r.snippet || r.text}</p>
        <div className="xp-badges">
          <TierBadge tier={r.authority_tier} long />
          {showStatus(r.doc_type, r.status) && <StatusBadge status={r.status} />}
          <TreatmentBadge treatment={r.treatment} />
          {r.court && <ExplorerBadge plain>{r.court}</ExplorerBadge>}
          {decided && <ExplorerBadge plain>{decided}</ExplorerBadge>}
        </div>
      </div>
      <div className="xp-scores" aria-label="Ranking scores">
        <ScoreMeter label="Relevance" value={r.ce_score} />
        <ScoreMeter label="Authority" value={r.authority_score} />
        <ScoreMeter label="Final" value={r.final_score} />
      </div>
    </li>
  );
}

function ScoreMeter({ label, value }: { label: string; value: number }) {
  const pct = scorePercent(normaliseScore(value));
  return (
    <div className="xp-score">
      <span>{label}</span>
      <span
        className="xp-meter"
        role="meter"
        aria-label={`${label} score`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
      >
        <i style={{ width: `${pct}%` }} />
      </span>
      <b>{formatScore(value)}</b>
    </div>
  );
}
