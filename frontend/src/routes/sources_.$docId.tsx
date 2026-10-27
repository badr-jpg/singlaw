import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ExternalLink, FileSearch, ListTree, MessageSquare } from "lucide-react";
import { toast } from "sonner";
import { PublicLayout } from "@/components/singlaw/shell";
import { Button } from "@/components/ui/button";
import { useIsMobile } from "@/hooks/use-mobile";
import { api } from "@/lib/api";
import { metadata } from "@/lib/singlaw";
import { ExplorerBadge, StatusBadge, TierBadge } from "@/components/singlaw/explorer/badges";
import {
  askAboutUrl,
  docTypeLabel,
  findLeaf,
  firstLeaf,
  formatDate,
  isLegislation,
  neighbourLeaves,
  showStatus,
} from "@/components/singlaw/explorer/helpers";
import { DocOutline } from "@/components/singlaw/explorer/outline";
import { ProvisionView } from "@/components/singlaw/explorer/provision";
import { errorMessage, isNotFound } from "@/components/singlaw/explorer/errors";
import { ExplorerEmpty, ExplorerError, LinesSkeleton } from "@/components/singlaw/explorer/states";
import { validateDocSearch } from "@/components/singlaw/explorer/search-params";
import "@/public.css";

/**
 * `sources_.$docId` keeps this page out of `/sources`'s render tree (the
 * explorer has no <Outlet/>), while still serving `/sources/$docId`.
 */
export const Route = createFileRoute("/sources_/$docId")({
  validateSearch: validateDocSearch,
  head: () =>
    metadata(
      "Read a document",
      "Read a provision or judgment passage from SingLaw's indexed corpus, with its status, authority tier, version history and citing judgments.",
    ),
  component: DocPage,
});

function DocPage() {
  const { docId } = Route.useParams();
  const { chunk } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const isMobile = useIsMobile();
  const [outlineOpen, setOutlineOpen] = useState(false);

  const doc = useQuery({
    queryKey: ["corpus-doc", docId],
    queryFn: () => api.corpusDoc(docId),
    retry: (count, error) => !isNotFound(error) && count < 2,
  });
  const tree = useMemo(() => doc.data?.tree ?? [], [doc.data]);
  const selected = useMemo(() => {
    if (!doc.data) return null;
    if (chunk && findLeaf(tree, chunk)) return chunk;
    return firstLeaf(tree)?.chunk_id ?? chunk ?? null;
  }, [doc.data, tree, chunk]);

  const provision = useQuery({
    queryKey: ["chunk", selected],
    queryFn: () => api.getChunk(selected as string),
    enabled: !!selected,
    retry: (count, error) => !isNotFound(error) && count < 2,
  });
  useEffect(() => {
    if (provision.error) toast.error(errorMessage(provision.error));
  }, [provision.error]);

  const select = (id: string) => {
    navigate({ search: { chunk: id }, replace: true });
    setOutlineOpen(false);
  };
  const neighbours = selected ? neighbourLeaves(tree, selected) : { previous: null, next: null };
  const showOutline = !isMobile || outlineOpen;

  return (
    <PublicLayout>
      <main className="public-page xp-doc-page enter">
        <Link to="/sources" className="xp-back">
          <ArrowLeft size={13} aria-hidden="true" /> All sources
        </Link>

        {doc.isPending ? (
          <div className="xp-doc-header" aria-busy="true">
            <LinesSkeleton lines={3} label="Loading document" />
          </div>
        ) : doc.error ? (
          isNotFound(doc.error) ? (
            <ExplorerEmpty
              icon={FileSearch}
              title="That document isn't in the corpus"
              action={
                <Button asChild variant="outline" size="sm">
                  <Link to="/sources">Browse the corpus</Link>
                </Button>
              }
            >
              <p>
                Nothing is indexed under “{docId}”. It may have been renamed in a sync, or it may
                not be part of the corpus yet.
              </p>
            </ExplorerEmpty>
          ) : (
            <ExplorerError
              title="The document didn't load"
              error={doc.error}
              retry={() => doc.refetch()}
            />
          )
        ) : (
          <>
            <header className="xp-doc-header">
              <div>
                <span className="eyebrow">{docTypeLabel(doc.data.doc_type)}</span>
                <h1>{doc.data.title}</h1>
                {doc.data.citation && doc.data.citation !== doc.data.title && (
                  <p className="xp-doc-citation">{doc.data.citation}</p>
                )}
                <div className="xp-badges">
                  {showStatus(doc.data.doc_type, doc.data.status) && (
                    <StatusBadge status={doc.data.status} />
                  )}
                  {provision.data && <TierBadge tier={provision.data.authority_tier} long />}
                  {doc.data.sso_version_date && (
                    <ExplorerBadge plain title="Date the SSO text is current to">
                      SSO version {formatDate(doc.data.sso_version_date)}
                    </ExplorerBadge>
                  )}
                </div>
              </div>
              <div className="xp-doc-actions">
                {doc.data.source_url && (
                  <Button asChild variant="outline" size="sm">
                    <a href={doc.data.source_url} target="_blank" rel="noreferrer">
                      Open on {isLegislation(doc.data.doc_type) ? "SSO" : "the official source"}{" "}
                      <ExternalLink />
                    </a>
                  </Button>
                )}
                <Button
                  size="sm"
                  onClick={() =>
                    window.location.assign(askAboutUrl(doc.data.citation || doc.data.title))
                  }
                >
                  <MessageSquare /> Ask about this{" "}
                  {doc.data.doc_type === "judgment" ? "judgment" : "document"}
                </Button>
              </div>
            </header>

            {tree.length === 0 ? (
              <ExplorerEmpty icon={ListTree} title="No text indexed for this document yet">
                <p>
                  The document is registered in the corpus but its provisions have not been chunked
                  yet. Try again after the next sync.
                </p>
              </ExplorerEmpty>
            ) : (
              <div className="xp-doc-layout">
                {isMobile && (
                  <Button
                    variant="outline"
                    className="xp-outline-mobile-toggle"
                    aria-expanded={outlineOpen}
                    aria-controls="xp-outline"
                    onClick={() => setOutlineOpen((o) => !o)}
                  >
                    <span className="inline-flex items-center gap-2">
                      <ListTree /> Outline
                    </span>
                    <span>{outlineOpen ? "Hide" : "Show"}</span>
                  </Button>
                )}
                <aside className="xp-outline" id="xp-outline" hidden={!showOutline}>
                  <DocOutline tree={tree} selected={selected} onSelect={select} />
                </aside>
                <section className="xp-provision" aria-live="polite">
                  {!selected ? (
                    <ExplorerEmpty icon={ListTree} title="Choose a provision from the outline" />
                  ) : provision.isPending ? (
                    <LinesSkeleton label="Loading provision" />
                  ) : provision.error ? (
                    <ExplorerError
                      title={
                        isNotFound(provision.error)
                          ? "That provision isn't indexed"
                          : "The provision didn't load"
                      }
                      error={provision.error}
                      retry={() => provision.refetch()}
                    />
                  ) : (
                    <ProvisionView
                      chunk={provision.data}
                      doc={doc.data}
                      previous={neighbours.previous}
                      next={neighbours.next}
                      onSelect={select}
                    />
                  )}
                </section>
              </div>
            )}
          </>
        )}
      </main>
    </PublicLayout>
  );
}
