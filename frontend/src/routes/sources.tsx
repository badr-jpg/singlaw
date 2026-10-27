import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  Database,
  LibraryBig,
  Search,
  SearchX,
  ShieldCheck,
  X,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import { PublicLayout } from "@/components/singlaw/shell";
import { SourceLogo, publisherForSource } from "@/components/singlaw/source-logo";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { api, type TocEntry } from "@/lib/api";
import { metadata } from "@/lib/singlaw";
import { StatusBadge, TierBadge } from "@/components/singlaw/explorer/badges";
import {
  DOC_TYPE_TABS,
  corpusSummary,
  docTypeLabel,
  formatCount,
  showStatus,
  tierLabel,
  type DocTypeFilter,
} from "@/components/singlaw/explorer/helpers";
import { LawSearch } from "@/components/singlaw/explorer/law-search";
import { errorMessage } from "@/components/singlaw/explorer/errors";
import { CardSkeletons, ExplorerEmpty, ExplorerError } from "@/components/singlaw/explorer/states";
import { useDebouncedValue } from "@/components/singlaw/explorer/use-debounced";
import {
  validateSourcesSearch,
  type SourcesSearch,
} from "@/components/singlaw/explorer/search-params";
import "@/public.css";

export const Route = createFileRoute("/sources")({
  validateSearch: validateSourcesSearch,
  head: () =>
    metadata(
      "Explore the corpus",
      "Browse and search every Act, regulation, Supreme Court judgment and Practice Direction SingLaw answers from — with status, authority tier, version history and citing cases.",
    ),
  component: Sources,
});

const PAGE = 60;

function Sources() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const mode: "browse" | "search" = search.mode === "search" ? "search" : "browse";
  const type: DocTypeFilter = search.type ?? "all";
  const q = search.q ?? "";

  const update = (patch: {
    mode?: "search" | null;
    q?: string | null;
    type?: DocTypeFilter | null;
  }) =>
    navigate({
      replace: true,
      search: (prev: SourcesSearch) => {
        const next: SourcesSearch = { ...prev };
        if (patch.mode !== undefined) {
          if (patch.mode) next.mode = patch.mode;
          else delete next.mode;
        }
        if (patch.q !== undefined) {
          if (patch.q && patch.q.trim()) next.q = patch.q.trim();
          else delete next.q;
        }
        if (patch.type !== undefined) {
          if (patch.type && patch.type !== "all") next.type = patch.type;
          else delete next.type;
        }
        return next;
      },
    });

  const health = useQuery({ queryKey: ["health"], queryFn: api.health, staleTime: 60_000 });

  return (
    <PublicLayout>
      <main className="public-page enter">
        <span className="eyebrow">The corpus explorer</span>
        <h1>
          Read the law.
          <br />
          <em className="editorial-accent">Straight from the source.</em>
        </h1>
        <p className="intro">
          Every answer SingLaw gives is retrieved from this corpus: Singapore Statutes Online
          legislation, Supreme Court judgments and Practice Directions. Browse it document by
          document, or search it the way the assistant does.
        </p>
        <p className="xp-stats" role="status">
          <Database aria-hidden="true" />
          {health.isPending ? (
            <span>Counting the corpus…</span>
          ) : health.error ? (
            <span>Corpus counts are unavailable right now.</span>
          ) : (
            <span>
              <strong>Indexed:</strong> {corpusSummary(health.data)}
              {health.data.corpus.repealed > 0 &&
                ` · ${formatCount(health.data.corpus.repealed)} repealed (flagged)`}
            </span>
          )}
        </p>

        <div className="xp-mode" role="tablist" aria-label="Explorer mode">
          <button
            type="button"
            role="tab"
            id="xp-tab-browse"
            aria-selected={mode === "browse"}
            aria-controls="xp-panel-browse"
            onClick={() => update({ mode: null })}
          >
            <LibraryBig aria-hidden="true" /> Browse documents
          </button>
          <button
            type="button"
            role="tab"
            id="xp-tab-search"
            aria-selected={mode === "search"}
            aria-controls="xp-panel-search"
            onClick={() => update({ mode: "search" })}
          >
            <Search aria-hidden="true" /> Search the law
          </button>
        </div>

        {mode === "browse" ? (
          <section
            className="xp-panel"
            role="tabpanel"
            id="xp-panel-browse"
            aria-labelledby="xp-tab-browse"
          >
            <BrowseCorpus
              q={q}
              type={type}
              onQuery={(value) => update({ q: value })}
              onType={(value) => update({ type: value })}
            />
          </section>
        ) : (
          <section
            className="xp-panel"
            role="tabpanel"
            id="xp-panel-search"
            aria-labelledby="xp-tab-search"
          >
            <LawSearch query={q} onSubmit={(value) => update({ q: value })} />
          </section>
        )}

        <p className="library-note">
          <ShieldCheck size={15} />
          Legislation is © Singapore Government, reproduced with the permission of the
          Attorney-General's Chambers under the Singapore Statutes Online terms of use. SSO text is
          not the authoritative text (s 48 Interpretation Act 1965); the Gazette is. Agency guidance
          from MOM, HDB, Customs and PDPC is on the roadmap and not indexed yet.
        </p>
      </main>
    </PublicLayout>
  );
}

function BrowseCorpus({
  q,
  type,
  onQuery,
  onType,
}: {
  q: string;
  type: DocTypeFilter;
  onQuery: (q: string) => void;
  onType: (type: DocTypeFilter) => void;
}) {
  const [draft, setDraft] = useState(q);
  const debounced = useDebouncedValue(draft, 300);
  useEffect(() => {
    if (debounced.trim() !== q) onQuery(debounced.trim());
    // onQuery is stable per render of the parent; q is what we compare against.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);
  useEffect(() => {
    setDraft((current) => (current.trim() === q ? current : q));
  }, [q]);

  const [shown, setShown] = useState(PAGE);
  useEffect(() => setShown(PAGE), [q, type]);

  const toc = useQuery({
    queryKey: ["corpus-toc", type, q],
    queryFn: () =>
      api.corpusToc({
        ...(type !== "all" ? { doc_type: type } : {}),
        ...(q ? { q } : {}),
      }),
    placeholderData: keepPreviousData,
  });
  useEffect(() => {
    if (toc.error) toast.error(errorMessage(toc.error));
  }, [toc.error]);

  const docs = toc.data ?? [];
  const reduced = useReducedMotion();
  const clear = () => {
    setDraft("");
    onType("all");
  };

  return (
    <>
      <div className="library-toolbar">
        <div className="library-search">
          <Search aria-hidden="true" />
          <Input
            placeholder="Search by title or citation…"
            aria-label="Search documents"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="pr-10"
            autoComplete="off"
          />
          {draft && (
            <Button
              variant="ghost"
              size="icon-xs"
              className="absolute right-2 top-2"
              aria-label="Clear search"
              onClick={() => setDraft("")}
            >
              <X size={12} />
            </Button>
          )}
        </div>
        <p className="library-count" role="status">
          {toc.isPending
            ? "Loading documents…"
            : `${formatCount(docs.length)} ${docs.length === 1 ? "document" : "documents"}${
                toc.isFetching ? " · updating…" : ""
              }`}
        </p>
      </div>
      <div className="library-filters" role="group" aria-label="Filter by document type">
        {DOC_TYPE_TABS.map((t) => (
          <button
            key={t.value}
            type="button"
            aria-pressed={type === t.value}
            onClick={() => onType(t.value)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {toc.isPending ? (
        <CardSkeletons />
      ) : toc.error && !toc.data ? (
        <ExplorerError
          title="The corpus didn't load"
          error={toc.error}
          retry={() => toc.refetch()}
        />
      ) : docs.length === 0 ? (
        <ExplorerEmpty
          icon={q ? SearchX : BookOpen}
          title={q ? `Nothing matches “${q}”` : "Nothing indexed here yet"}
          action={
            <Button variant="outline" size="sm" onClick={clear}>
              Clear filters
            </Button>
          }
        >
          <p>
            {q
              ? "Try a shorter title, a citation such as “[2022] SGCA 60”, or another document type."
              : `No ${docTypeLabel(type).toLowerCase()} documents are in the corpus yet.`}
          </p>
        </ExplorerEmpty>
      ) : (
        <>
          <div className="library-grid">
            {docs.slice(0, shown).map((d) => (
              <DocCard key={d.doc_id} doc={d} reduced={!!reduced} />
            ))}
          </div>
          {docs.length > shown && (
            <div className="xp-more">
              <Button variant="outline" onClick={() => setShown((n) => n + PAGE)}>
                Show more ({formatCount(docs.length - shown)} remaining)
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}

function DocCard({ doc, reduced }: { doc: TocEntry; reduced: boolean }) {
  const showCitation = doc.citation && doc.citation !== doc.title;
  return (
    <motion.article
      className="source-card xp-card"
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <div className="source-card-head">
        <SourceLogo id={publisherForSource(doc.doc_type)} />
        <span className="eyebrow">{docTypeLabel(doc.doc_type)}</span>
      </div>
      <h3>{doc.title}</h3>
      <p className={showCitation ? "xp-citation" : ""}>
        {showCitation ? doc.citation : tierLabel(doc.authority_tier)}
      </p>
      <div className="xp-badges xp-card-meta">
        {showStatus(doc.doc_type, doc.status) && <StatusBadge status={doc.status} />}
        {doc.doc_type === "judgment" && <TierBadge tier={doc.authority_tier} />}
      </div>
      <Link
        to="/sources/$docId"
        params={{ docId: doc.doc_id }}
        className="xp-card-link"
        aria-label={`Open ${doc.title}`}
      >
        Read in the explorer
        <ArrowRight size={15} />
      </Link>
    </motion.article>
  );
}
