import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  ArrowUpRight,
  ArrowRight,
  Trash2,
  PanelLeftClose,
  Globe,
  SquarePen,
  ExternalLink,
  MessageSquare,
  ShieldCheck,
  Sparkles,
  Pencil,
  FileText,
} from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { useIsMobile } from "@/hooks/use-mobile";
import { api, type ConversationSummary } from "@/lib/api";
import {
  docTypeLabel,
  formatDate,
  formatDateTime,
  groupConversations,
  isLegislation,
  relativeTime,
} from "@/lib/singlaw";
import { useHistory } from "./history-context";
import { SourceLogo, publisherForSource } from "./source-logo";
import { ThemeMenu } from "./theme-menu";
import { SingaporeFlag } from "./singapore-flag";
import { StatusBadge, TierBadge, TreatmentBadge, MetaChip } from "./trust/badges";
import { Attribution } from "./trust/surfaces";
import type { SourceRef } from "./workspace/answer-context";

export function Brand() {
  return (
    <span className="sidebar-brand">
      <span className="brand-mark" aria-hidden="true">
        §
      </span>
      <span>
        SingLaw<span className="brand-period">.</span>
      </span>
    </span>
  );
}

function ThreadRow({
  conversation,
  active,
  onNavigate,
  onRename,
  onDelete,
}: {
  conversation: ConversationSummary;
  active: boolean;
  onNavigate: () => void;
  onRename: (title: string) => Promise<void>;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(conversation.title);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (editing) input.current?.select();
  }, [editing]);

  const begin = () => {
    setDraft(conversation.title);
    setEditing(true);
  };
  const commit = async () => {
    setEditing(false);
    const title = draft.trim();
    if (!title || title === conversation.title) return;
    try {
      await onRename(title);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "The conversation could not be renamed.");
    }
  };
  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void commit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      setEditing(false);
    }
  };

  return (
    <div className={`thread-row ${active ? "active" : ""}`}>
      <MessageSquare className="thread-icon" size={14} />
      {editing ? (
        <input
          ref={input}
          className="thread-rename"
          aria-label="Conversation title"
          value={draft}
          maxLength={120}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          onBlur={() => void commit()}
        />
      ) : (
        <Link
          to="/chat/$threadId"
          params={{ threadId: conversation.id }}
          className="thread-link"
          onClick={onNavigate}
          onDoubleClick={(event) => {
            event.preventDefault();
            begin();
          }}
          aria-current={active ? "page" : undefined}
          title={conversation.title}
        >
          {conversation.title || "Untitled conversation"}
        </Link>
      )}
      {!editing && (
        <span className="thread-actions">
          <Button
            size="icon-xs"
            variant="ghost"
            title="Rename conversation"
            aria-label={`Rename ${conversation.title}`}
            onClick={begin}
          >
            <Pencil className="size-3" />
          </Button>
          <Button
            size="icon-xs"
            variant="ghost"
            title="Delete conversation"
            aria-label={`Delete ${conversation.title}`}
            onClick={onDelete}
          >
            <Trash2 className="size-3" />
          </Button>
        </span>
      )}
    </div>
  );
}

function SidebarStatus() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
    retry: 1,
  });
  const data = health.data;
  const tone = health.isError
    ? "down"
    : !data
      ? "pending"
      : data.status === "ok"
        ? "ok"
        : "degraded";
  const label = health.isError
    ? "SingLaw is unreachable"
    : !data
      ? "Checking the corpus…"
      : data.last_sync
        ? `Corpus synced ${relativeTime(data.last_sync)}`
        : "Corpus not yet synced";
  const detail = data
    ? `${data.corpus.acts} Acts · ${data.corpus.subsidiary_legislation} subsidiary legislation · ${data.corpus.judgments} judgments${
        data.last_sync ? ` · synced ${formatDateTime(data.last_sync)}` : ""
      }${data.status === "degraded" ? " · service degraded" : ""}`
    : undefined;
  return (
    <div className="sidebar-status">
      <span className="status-dot" data-tone={tone} aria-hidden="true" />
      <span className="sidebar-status-text" title={detail}>
        {label}
      </span>
      <ThemeMenu />
    </div>
  );
}

export function ChatShell({
  children,
  threadId,
  mobileOpen,
  closeMobile,
  source,
  closeSource,
  businesses,
}: {
  children: ReactNode;
  threadId?: string | undefined;
  mobileOpen: boolean;
  closeMobile: () => void;
  source?: SourceRef | null | undefined;
  closeSource: () => void;
  businesses?: ReactNode;
}) {
  const { conversations, ready, error, rename, remove } = useHistory();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [pendingDelete, setPendingDelete] = useState<ConversationSummary | null>(null);
  const [deleting, setDeleting] = useState(false);

  const onNavigate = () => {
    if (isMobile) closeMobile();
  };
  const newChat = () => {
    navigate({ to: "/" });
    onNavigate();
  };
  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await remove(pendingDelete.id);
      if (threadId === pendingDelete.id) navigate({ to: "/" });
      setPendingDelete(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "The conversation could not be deleted.");
    } finally {
      setDeleting(false);
    }
  };

  const groups = groupConversations(conversations);
  const navigation = (
    <>
      <div className="sidebar-heading">
        <Link to="/" onClick={onNavigate} aria-label="SingLaw home">
          <Brand />
        </Link>
        {!isMobile && (
          <Button
            variant="ghost"
            size="icon-sm"
            className="sidebar-collapse"
            onClick={closeMobile}
            aria-label="Hide navigation"
            title="Hide navigation"
          >
            <PanelLeftClose />
          </Button>
        )}
      </div>
      <Button variant="ghost" className="sidebar-new" onClick={newChat}>
        <SquarePen /> New conversation
      </Button>
      <div className="thread-list">
        <div className="sidebar-section-label">
          <span>Conversations</span>
          <span>{conversations.length || ""}</span>
        </div>
        {!ready ? (
          <p className="history-loading">
            <Shimmer>Loading conversations…</Shimmer>
          </p>
        ) : error && conversations.length === 0 ? (
          <div className="history-empty">
            <MessageSquare size={20} strokeWidth={1.4} />
            <p>Conversations unavailable</p>
            <span>{error}</span>
          </div>
        ) : conversations.length === 0 ? (
          <div className="history-empty">
            <MessageSquare size={20} strokeWidth={1.4} />
            <p>Your next step starts here.</p>
            <span>Start with a trending question or ask your own.</span>
          </div>
        ) : (
          groups.map((group) => (
            <section key={group.label} aria-label={group.label}>
              <h3 className="thread-group-label">{group.label}</h3>
              {group.items.map((conversation) => (
                <ThreadRow
                  key={conversation.id}
                  conversation={conversation}
                  active={conversation.id === threadId}
                  onNavigate={onNavigate}
                  onRename={(title) => rename(conversation.id, title)}
                  onDelete={() => setPendingDelete(conversation)}
                />
              ))}
            </section>
          ))
        )}
      </div>
      {businesses && <div className="sidebar-businesses">{businesses}</div>}
      <Link to="/billing" className="sidebar-plan" onClick={onNavigate}>
        <span className="sidebar-plan-icon">
          <Sparkles size={16} />
        </span>
        <span>
          <strong>A little more possibility</strong>
          <small>Explore plans for every chapter</small>
        </span>
        <ArrowUpRight size={15} />
      </Link>
      <nav className="sidebar-footer" aria-label="Workspace resources">
        <Link to="/sources" onClick={onNavigate}>
          <BookOpen size={16} /> Source library <ArrowUpRight size={13} className="ml-auto" />
        </Link>
        <Link to="/welcome" onClick={onNavigate}>
          <Globe size={16} /> Meet SingLaw
        </Link>
      </nav>
      <SidebarStatus />
    </>
  );
  return (
    <div className={`app-shell ${mobileOpen ? "navigation-open" : "navigation-closed"}`}>
      {isMobile ? (
        <Sheet
          open={mobileOpen}
          onOpenChange={(open) => {
            if (!open) closeMobile();
          }}
        >
          <SheetContent
            side="left"
            className="mobile-navigation"
            onCloseAutoFocus={(event) => {
              event.preventDefault();
              document.getElementById("navigation-toggle")?.focus();
            }}
          >
            <SheetTitle className="sr-only">Workspace navigation</SheetTitle>
            <SheetDescription className="sr-only">
              Your conversations, businesses and resources.
            </SheetDescription>
            {navigation}
          </SheetContent>
        </Sheet>
      ) : (
        <aside className="sidebar" aria-label="Workspace navigation" inert={!mobileOpen}>
          {navigation}
        </aside>
      )}
      {children}
      {source && <SourceDrawer source={source} close={closeSource} />}
      <AlertDialog
        open={!!pendingDelete}
        onOpenChange={(open) => {
          if (!open && !deleting) setPendingDelete(null);
        }}
      >
        <AlertDialogContent className="singlaw-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              “{pendingDelete?.title}” and its answers will be removed from your workspace. This
              cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Keep it</AlertDialogCancel>
            <AlertDialogAction
              className="confirm-destructive"
              disabled={deleting}
              onClick={(event) => {
                event.preventDefault();
                void confirmDelete();
              }}
            >
              {deleting ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function publisherName(id: string): string {
  switch (id) {
    case "courts":
      return "Singapore Courts";
    case "mom":
      return "Ministry of Manpower";
    case "hdb":
      return "Housing & Development Board";
    case "customs":
      return "Singapore Customs";
    default:
      return "Singapore Statutes Online";
  }
}

/** Right-hand drawer with the full text and metadata of a cited chunk. */
export function SourceDrawer({ source, close }: { source: SourceRef; close: () => void }) {
  const opener = useRef(
    typeof document !== "undefined" ? (document.activeElement as HTMLElement | null) : null,
  );
  const chunk = useQuery({
    queryKey: ["chunk", source.chunk_id],
    queryFn: () => api.getChunk(source.chunk_id),
    staleTime: Number.POSITIVE_INFINITY,
  });
  const merged = { ...source, ...(chunk.data ?? {}) };
  const userDoc = merged.collection === "user_docs";
  const docType = merged.doc_type ?? "";
  const publisher = userDoc ? "doc" : publisherForSource(docType, merged.url);
  const hierarchy = merged.hierarchy_path ?? [];
  const text = chunk.data?.text ?? merged.snippet ?? "";
  const legislation = !userDoc && !!docType && isLegislation(docType, merged.collection);

  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <SheetContent
        className="reference-drawer"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          opener.current?.focus();
        }}
      >
        <div className="reference-kicker">
          <BookOpen size={15} /> {userDoc ? "From your document" : "Behind the answer"}
        </div>
        <div className="source-publisher">
          {userDoc ? (
            <span className="source-logo source-icon-fallback" aria-hidden="true">
              <FileText />
            </span>
          ) : (
            <SourceLogo id={publisher} />
          )}
          {userDoc ? "Your document" : publisherName(publisher)}
        </div>
        <SheetTitle className="reference-title">
          {userDoc ? `Your document — ${merged.citation}` : merged.citation}
        </SheetTitle>
        {hierarchy.length > 0 && (
          <nav aria-label="Hierarchy" className="reference-breadcrumb">
            {hierarchy.map((segment, i) => (
              <span key={`${i}-${segment}`}>
                {i > 0 && <span className="crumb-divider">›</span>}
                {segment}
              </span>
            ))}
          </nav>
        )}
        <div className="reference-badges">
          {typeof merged.authority_tier === "number" && !userDoc && (
            <TierBadge tier={merged.authority_tier} compact={false} />
          )}
          {merged.status && !userDoc && <StatusBadge status={merged.status} />}
          {merged.treatment && <TreatmentBadge treatment={merged.treatment} />}
          {userDoc && <MetaChip tone="scope">Your material — not legal authority</MetaChip>}
        </div>
        {(docType || merged.court || merged.decision_date) && (
          <dl className="reference-facts">
            {docType && (
              <>
                <dt>Type</dt>
                <dd>{userDoc ? "Uploaded document" : docTypeLabel(docType)}</dd>
              </>
            )}
            {merged.court && (
              <>
                <dt>Court</dt>
                <dd>{merged.court}</dd>
              </>
            )}
            {merged.decision_date && (
              <>
                <dt>Decided</dt>
                <dd>{formatDate(merged.decision_date)}</dd>
              </>
            )}
          </dl>
        )}
        <SheetDescription className="sr-only">
          {userDoc ? "Passage from your uploaded document." : "The cited provision or paragraph."}
        </SheetDescription>
        {chunk.data?.context && <p className="reference-context">{chunk.data.context}</p>}
        <div className="provision-text" aria-busy={chunk.isPending}>
          {text ? (
            text
          ) : chunk.isPending ? (
            <Shimmer>Loading the provision…</Shimmer>
          ) : (
            <span className="text-muted-foreground">No text is available for this source.</span>
          )}
        </div>
        {chunk.error && (
          <p className="reference-error">
            The full text could not be loaded ({chunk.error.message}).
            {merged.snippet ? " Showing the retrieved excerpt instead." : ""}
          </p>
        )}
        {merged.url && !userDoc && (
          <Button asChild className="reference-link">
            <a href={merged.url} target="_blank" rel="noreferrer">
              Open official source <ExternalLink size={15} />
            </a>
          </Button>
        )}
        {userDoc ? (
          <div className="reference-note">
            <ShieldCheck size={19} />
            <div>
              <strong>Your own material.</strong>
              <p>
                This passage comes from a document you uploaded. It gives answers context about your
                situation but is not legal authority.
              </p>
            </div>
          </div>
        ) : (
          <div className="reference-note">
            <ShieldCheck size={19} />
            <div>
              <strong>Read the source, not just the summary.</strong>
              <p>
                SingLaw cites the exact provision or paragraph it relied on. The official text
                always prevails over any answer.
              </p>
            </div>
          </div>
        )}
        {legislation && <Attribution className="reference-attribution" />}
        <Link to="/sources" className="reference-library" onClick={close}>
          Explore the source library <ArrowRight size={14} />
        </Link>
      </SheetContent>
    </Sheet>
  );
}

export function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <header className="public-header">
        <Link to="/" aria-label="SingLaw home">
          <Brand />
        </Link>
        <nav aria-label="Main navigation">
          <Link to="/welcome" className="about-link" activeProps={{ "aria-current": "page" }}>
            Meet SingLaw
          </Link>
          <Link to="/sources" className="about-link" activeProps={{ "aria-current": "page" }}>
            Sources
          </Link>
          <ThemeMenu />
          <Link to="/billing" activeProps={{ "aria-current": "page" }}>
            Plans
          </Link>
          <Button asChild>
            <Link to="/">
              Ask SingLaw <ArrowUpRight />
            </Link>
          </Button>
        </nav>
      </header>
      {children}
      <footer className="public-footer">
        <span>© 2026 SingLaw. Clarity, with context.</span>
        <nav aria-label="Footer navigation">
          <Link to="/sources">Sources</Link>
          <Link to="/terms">Terms & privacy</Link>
          <span className="singapore-signoff">
            <SingaporeFlag /> Made for Singapore.
          </span>
        </nav>
      </footer>
    </>
  );
}

export function Modal({
  title,
  children,
  close,
  eyebrow,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  eyebrow: string;
}) {
  const opener = useRef(
    typeof document !== "undefined" ? (document.activeElement as HTMLElement) : null,
  );
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent
        className="singlaw-modal"
        aria-describedby={undefined}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          opener.current?.focus();
        }}
      >
        <span className="eyebrow">{eyebrow}</span>
        <DialogTitle>{title}</DialogTitle>
        {children}
      </DialogContent>
    </Dialog>
  );
}
