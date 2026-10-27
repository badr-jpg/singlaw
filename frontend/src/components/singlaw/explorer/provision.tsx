import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ExternalLink,
  History,
  MessageSquare,
  Scale,
} from "lucide-react";
import { toast } from "sonner";
import { api, type Chunk, type CitingJudgment, type CorpusDoc, type DocTreeNode } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AgcAttribution } from "./agc-attribution";
import { ExplorerBadge, StatusBadge, TierBadge, TreatmentBadge } from "./badges";
import {
  askAboutUrl,
  formatDate,
  formatDateTime,
  isFlagged,
  isLegislation,
  showStatus,
  treatmentLabel,
} from "./helpers";
import { errorMessage, isNotFound } from "./errors";
import { LinesSkeleton } from "./states";

export function ProvisionView({
  chunk,
  doc,
  previous,
  next,
  onSelect,
}: {
  chunk: Chunk;
  doc: CorpusDoc;
  previous: DocTreeNode | null;
  next: DocTreeNode | null;
  onSelect: (chunkId: string) => void;
}) {
  const legislation = isLegislation(chunk.doc_type);
  const judgment = chunk.doc_type === "judgment";
  const path = chunk.hierarchy_path.length ? chunk.hierarchy_path : [doc.title];
  const heading = path[path.length - 1] ?? chunk.citation;
  const flagged = isFlagged(chunk.status, chunk.treatment);
  const officialUrl = chunk.url || doc.source_url;
  const historyCitation = doc.citation || chunk.citation;
  const citingCitation = judgment ? doc.citation || chunk.citation : chunk.citation;
  const decided = formatDate(chunk.decision_date);

  return (
    <article className="enter" key={chunk.chunk_id}>
      <ol className="xp-breadcrumb" aria-label="Position in the document">
        {path.map((p, i) => (
          <li key={`${i}-${p}`}>{p}</li>
        ))}
      </ol>
      <h2>{heading}</h2>
      <div className="xp-badges">
        <TierBadge tier={chunk.authority_tier} long />
        {showStatus(chunk.doc_type, chunk.status) && <StatusBadge status={chunk.status} />}
        <TreatmentBadge treatment={chunk.treatment} />
        {chunk.court && <ExplorerBadge plain>{chunk.court}</ExplorerBadge>}
        {decided && <ExplorerBadge plain>Decided {decided}</ExplorerBadge>}
      </div>
      {flagged && (
        <p className="xp-flag" role="status">
          <AlertTriangle size={15} aria-hidden="true" />
          <span>
            {chunk.status === "repealed"
              ? "This legislation is repealed. SingLaw never serves repealed authority as current law; it is shown here for the record."
              : "This judgment has been overruled. SingLaw never serves overruled authority as current law; it is shown here for the record."}
          </span>
        </p>
      )}
      <div className="xp-provision-text">{chunk.text}</div>
      {chunk.context && <p className="xp-context">{chunk.context}</p>}
      <div className="xp-provision-actions">
        {officialUrl && (
          <Button asChild variant="outline" size="sm">
            <a href={officialUrl} target="_blank" rel="noreferrer">
              Open on {legislation ? "SSO" : "the official source"} <ExternalLink />
            </a>
          </Button>
        )}
        <Button size="sm" onClick={() => window.location.assign(askAboutUrl(chunk.citation))}>
          <MessageSquare /> Ask about this {judgment ? "passage" : "provision"}
        </Button>
        <div className="xp-pager">
          <Button
            variant="ghost"
            size="sm"
            disabled={!previous?.chunk_id}
            onClick={() => previous?.chunk_id && onSelect(previous.chunk_id)}
            aria-label={previous ? `Previous: ${previous.label}` : "No previous provision"}
          >
            <ArrowLeft /> Previous
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={!next?.chunk_id}
            onClick={() => next?.chunk_id && onSelect(next.chunk_id)}
            aria-label={next ? `Next: ${next.label}` : "No next provision"}
          >
            Next <ArrowRight />
          </Button>
        </div>
      </div>
      {legislation && <AgcAttribution />}
      <Tabs defaultValue="history" className="xp-tabs">
        <TabsList aria-label="More about this provision">
          <TabsTrigger value="history">
            <History size={13} className="mr-1.5" aria-hidden="true" /> Version history
          </TabsTrigger>
          <TabsTrigger value="citing">
            <Scale size={13} className="mr-1.5" aria-hidden="true" /> Citing judgments
          </TabsTrigger>
        </TabsList>
        <TabsContent value="history">
          <HistoryPanel citation={historyCitation} legislation={legislation} />
        </TabsContent>
        <TabsContent value="citing">
          <CitingPanel citation={citingCitation} />
        </TabsContent>
      </Tabs>
    </article>
  );
}

function HistoryPanel({ citation, legislation }: { citation: string; legislation: boolean }) {
  const history = useQuery({
    queryKey: ["law-history", citation],
    queryFn: () => api.getLawHistory(citation),
    enabled: !!citation,
    retry: false,
  });
  if (history.isPending) return <LinesSkeleton lines={3} label="Loading version history" />;
  if (history.error) {
    return (
      <p className="xp-empty-inline">
        {isNotFound(history.error)
          ? "No version history is recorded for this citation."
          : errorMessage(history.error)}
      </p>
    );
  }
  const versions = history.data.versions;
  if (!versions.length) return <p className="xp-empty-inline">No versions recorded yet.</p>;
  return (
    <>
      <p className="xp-panel-note">
        {legislation
          ? "Each entry is a version SingLaw fetched from Singapore Statutes Online, newest first. The SSO version date is the date the text is current to."
          : "When SingLaw fetched this document from its official source, newest first."}
      </p>
      <ol className="xp-timeline">
        {versions.map((v, i) => (
          <li key={`${v.sso_version_date ?? "none"}-${v.fetched_at}-${i}`}>
            <strong>
              {v.sso_version_date
                ? `SSO version dated ${formatDate(v.sso_version_date)}`
                : "Version date not stated by the source"}
            </strong>
            <span>Fetched {formatDateTime(v.fetched_at) ?? "—"}</span>
            {v.source_url && (
              <a href={v.source_url} target="_blank" rel="noreferrer">
                Open this version <ExternalLink size={11} />
              </a>
            )}
          </li>
        ))}
      </ol>
    </>
  );
}

function CitingPanel({ citation }: { citation: string }) {
  const navigate = useNavigate();
  const [resolving, setResolving] = useState<string | null>(null);
  const citing = useQuery({
    queryKey: ["law-citing", citation],
    queryFn: () => api.getLawCiting(citation),
    enabled: !!citation,
    retry: false,
  });

  const open = async (c: CitingJudgment) => {
    setResolving(c.citation);
    try {
      const entries = await api.corpusToc({ q: c.citation });
      const hit =
        entries.find((e) => e.citation === c.citation) ??
        entries.find((e) => e.doc_type === "judgment" && e.title.includes(c.citation)) ??
        entries.find((e) => e.doc_type === "judgment");
      if (hit) {
        navigate({ to: "/sources/$docId", params: { docId: hit.doc_id } });
      } else {
        toast.info(`${c.citation} is cited here but is not in the indexed corpus yet.`);
      }
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setResolving(null);
    }
  };

  if (citing.isPending) return <LinesSkeleton lines={3} label="Loading citing judgments" />;
  if (citing.error) return <p className="xp-empty-inline">{errorMessage(citing.error)}</p>;
  const rows = citing.data.citing;
  if (!rows.length) {
    return (
      <p className="xp-empty-inline">
        No indexed judgment cites this provision yet. Citations are extracted from the Supreme Court
        judgments in the corpus, so this list grows as the corpus does.
      </p>
    );
  }
  return (
    <>
      <p className="xp-panel-note">
        Judgments in the corpus that cite this provision, newest first. The treatment shown is how
        that judgment treated it; “overruled” and “distinguished” are flagged.
      </p>
      <ul className="xp-citing">
        {rows.map((c, i) => {
          const date = formatDate(c.decision_date);
          const treatment = treatmentLabel(c.treatment);
          return (
            <li key={`${c.citation}-${c.paragraph ?? i}`}>
              <div>
                <button type="button" onClick={() => open(c)} disabled={resolving === c.citation}>
                  {c.case_name ? `${c.case_name} ${c.citation}` : c.citation}
                </button>
                <small>
                  {[c.court, date, c.paragraph != null ? `at [${c.paragraph}]` : null]
                    .filter(Boolean)
                    .join(" · ")}
                  {resolving === c.citation ? " · opening…" : ""}
                </small>
              </div>
              {treatment && <TreatmentBadge treatment={c.treatment} />}
            </li>
          );
        })}
      </ul>
    </>
  );
}
