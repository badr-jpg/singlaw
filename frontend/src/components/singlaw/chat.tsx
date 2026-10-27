import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Menu, Sparkles } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputFooter,
} from "@/components/ai-elements/prompt-input";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { api, ApiError, type ChatRequest } from "@/lib/api";
import { useChatStream } from "@/lib/chat-stream";
import {
  DEFAULT_DOCUMENT_QUESTION,
  DISCLAIMER_TEXT,
  MAX_UPLOAD_BYTES,
  UPLOAD_TYPE_MESSAGE,
  isAllowedUpload,
  messagesFromConversation,
  textForClipboard,
  type MessageAttachment,
  type UiMessage,
} from "@/lib/singlaw";
import { useWorkspaceScope } from "@/hooks/use-workspace-scope";
import { useDocumentUploads } from "@/hooks/use-document-uploads";
import { ThemeMenu } from "./theme-menu";
import { ChatShell } from "./shell";
import { useHistory } from "./history-context";
import { BusinessPicker, BUSINESSES_KEY } from "./businesses";
import { ChatWelcome, PromptSuggestions, WorkspaceSources } from "./chat-start";
import { AssistantMessage } from "./workspace/assistant-message";
import { UserMessage } from "./workspace/user-message";
import type { SourceRef } from "./workspace/answer-context";
import {
  Attachments,
  ComposerSubmit,
  ScopeChip,
  UploadButton,
  UploadProgress,
  type ComposerStatus,
} from "./workspace/composer-bits";

type Phase = "idle" | "uploading" | "creating" | "submitted" | "streaming";

interface StreamRequest {
  conversationId: string;
  question: string;
  docIds: string[] | null;
  businessId: string | null;
  regenerate?: boolean;
}

let localCounter = 0;
const localId = (prefix: string) => `${prefix}-${Date.now()}-${++localCounter}`;

/** What the composer hands over on submit: a data/blob URL per attachment. */
interface SubmittedFile {
  url: string;
  filename?: string | undefined;
  mediaType?: string | undefined;
}

/** Rebuild a File from the data/blob URL the composer hands over on submit. */
async function toFile(part: SubmittedFile): Promise<File | null> {
  try {
    const res = await fetch(part.url);
    const blob = await res.blob();
    return new File([blob], part.filename ?? "document", { type: part.mediaType || blob.type });
  } catch {
    return null;
  }
}

export function ChatPage({
  threadId,
  initialQuestion,
}: {
  threadId?: string;
  initialQuestion?: string | undefined;
}) {
  const { conversations, create, refresh, stashPending, takePending } = useHistory();
  const queryClient = useQueryClient();
  const reduced = useReducedMotion();
  const navigate = useNavigate();
  const scope = useWorkspaceScope();
  const { send: sendStream, stop: stopStream } = useChatStream();
  const uploads = useDocumentUploads();

  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState(initialQuestion ?? "");
  const [phase, setPhase] = useState<Phase>("idle");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [source, setSource] = useState<SourceRef | null>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const wowIndex = useRef(0);

  const businesses = useQuery({
    queryKey: BUSINESSES_KEY,
    queryFn: api.listBusinesses,
    staleTime: 60_000,
  });
  const business = scope.businessId
    ? (businesses.data?.find((b) => b.id === scope.businessId) ?? null)
    : null;
  const activeBusinessId = scope.mode === "business" && business ? business.id : null;

  // The thread always loads fresh on mount: local state is authoritative while mounted.
  const detail = useQuery({
    queryKey: ["conversation", threadId],
    queryFn: () => api.getConversation(threadId!),
    enabled: !!threadId,
    staleTime: 0,
    gcTime: 0,
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });
  const notFound = detail.error instanceof ApiError && detail.error.status === 404;
  const hydrated = useRef(false);
  useEffect(() => {
    if (hydrated.current || !detail.data) return;
    hydrated.current = true;
    setMessages(messagesFromConversation(detail.data));
  }, [detail.data]);

  // Desktop opens the navigation and focuses the composer.
  useEffect(() => {
    const desktop = matchMedia("(min-width: 768px)").matches;
    setMobileOpen(desktop);
    if (desktop) textarea.current?.focus();
  }, []);

  // Abort an in-flight answer when the page really unmounts (StrictMode re-runs are skipped).
  const stopRef = useRef(stopStream);
  stopRef.current = stopStream;
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      setTimeout(() => {
        if (!mounted.current) stopRef.current();
      }, 0);
    };
  }, []);

  const patchMessage = useCallback((id: string, fn: (m: UiMessage) => UiMessage) => {
    setMessages((all) => all.map((m) => (m.id === id ? fn(m) : m)));
  }, []);

  const runStream = useCallback(
    (req: StreamRequest) => {
      const assistantId = localId("a");
      setMessages((all) => [
        ...all,
        {
          id: assistantId,
          role: "assistant",
          text: "",
          createdAt: new Date().toISOString(),
          sources: [],
          streaming: true,
          question: req.question,
          docIds: req.docIds,
        },
      ]);
      setPhase("submitted");
      const finish = (extra: Partial<UiMessage>) => {
        patchMessage(assistantId, (m) => ({ ...m, ...extra, streaming: false }));
        setPhase("idle");
        refresh();
        textarea.current?.focus();
      };
      const body: ChatRequest = {
        message: req.regenerate ? "" : req.question,
        conversation_id: req.conversationId,
        doc_ids: req.docIds,
        business_id: req.businessId,
        ...(req.regenerate ? { regenerate: true } : {}),
      };
      void sendStream(body, {
        onMeta: (meta) => {
          if (meta.conversation_id && meta.conversation_id !== req.conversationId) return;
          patchMessage(assistantId, (m) => ({
            ...m,
            meta,
            serverId: meta.message_id || m.serverId,
          }));
        },
        onSources: ({ sources }) =>
          patchMessage(assistantId, (m) => ({ ...m, sources: sources ?? [] })),
        onToken: ({ text }) => {
          setPhase("streaming");
          patchMessage(assistantId, (m) => ({ ...m, text: m.text + text }));
        },
        onValidation: (validation) => patchMessage(assistantId, (m) => ({ ...m, validation })),
        onDone: (done) => finish({ serverId: done.message_id, timings: done.timings_ms }),
        onError: (message) => {
          toast.error(message);
          finish({ error: message });
        },
        onAbort: () => finish({ aborted: true }),
      });
    },
    [patchMessage, refresh, sendStream],
  );
  const runStreamRef = useRef(runStream);
  runStreamRef.current = runStream;

  // A question captured on "/" is answered as soon as its new thread mounts.
  const kickedOff = useRef(false);
  useEffect(() => {
    if (!threadId || kickedOff.current) return;
    const pending = takePending(threadId);
    if (!pending) return;
    kickedOff.current = true;
    hydrated.current = true;
    setMessages([
      {
        id: localId("u"),
        role: "user",
        text: pending.question,
        createdAt: new Date().toISOString(),
        sources: [],
        attachments: pending.attachments,
      },
    ]);
    runStreamRef.current({
      conversationId: threadId,
      question: pending.question,
      docIds: pending.docIds,
      businessId: pending.businessId,
    });
  }, [threadId, takePending]);

  const send = useCallback(
    async (text: string, files: SubmittedFile[]) => {
      if (phase !== "idle" || notFound) return;
      const trimmed = text.trim();
      if (!trimmed && files.length === 0) return;
      if (files.some((f) => !isAllowedUpload(f.filename ?? ""))) {
        toast.error(UPLOAD_TYPE_MESSAGE);
        return;
      }
      const question = trimmed || DEFAULT_DOCUMENT_QUESTION;
      setInput("");

      let attachments: MessageAttachment[] = [];
      let docIds: string[] | null = null;
      if (files.length > 0) {
        setPhase("uploading");
        const fileObjects = (await Promise.all(files.map(toFile))).filter((f): f is File => !!f);
        if (fileObjects.length < files.length) toast.error("Some attachments could not be read.");
        const outcome = await uploads.uploadAll(fileObjects, activeBusinessId);
        for (const failed of outcome.failed) toast.error(`${failed.filename}: ${failed.error}`);
        uploads.reset();
        attachments = outcome.ready;
        docIds = attachments.length > 0 ? attachments.map((a) => a.id) : null;
        if (attachments.length === 0 && !trimmed) {
          setPhase("idle");
          return;
        }
      }

      if (!threadId) {
        setPhase("creating");
        try {
          const created = await create(question.slice(0, 60));
          stashPending(created.id, { question, docIds, businessId: activeBusinessId, attachments });
          await navigate({ to: "/chat/$threadId", params: { threadId: created.id } });
        } catch (err) {
          toast.error(
            err instanceof Error ? err.message : "The conversation could not be started.",
          );
          setPhase("idle");
        }
        return;
      }

      setMessages((all) => [
        ...all,
        {
          id: localId("u"),
          role: "user",
          text: question,
          createdAt: new Date().toISOString(),
          sources: [],
          ...(attachments.length > 0 ? { attachments } : {}),
        },
      ]);
      runStream({ conversationId: threadId, question, docIds, businessId: activeBusinessId });
    },
    [
      phase,
      notFound,
      threadId,
      activeBusinessId,
      uploads,
      create,
      stashPending,
      navigate,
      runStream,
    ],
  );

  const regenerate = (message: UiMessage) => {
    if (!threadId || phase !== "idle") return;
    const index = messages.findIndex((m) => m.id === message.id);
    const asked = [...messages.slice(0, index)].reverse().find((m) => m.role === "user");
    const question = asked?.text ?? message.question ?? "";
    setMessages((all) => all.filter((m) => m.id !== message.id));
    runStream({
      conversationId: threadId,
      question,
      docIds: message.docIds ?? null,
      businessId: activeBusinessId,
      regenerate: true,
    });
  };

  const feedback = async (message: UiMessage, rating: "up" | "down") => {
    const id = message.serverId ?? message.id;
    const previous = message.feedback ?? null;
    patchMessage(message.id, (m) => ({ ...m, feedback: rating }));
    try {
      await api.sendFeedback(id, rating);
    } catch (err) {
      patchMessage(message.id, (m) => ({ ...m, feedback: previous }));
      toast.error(err instanceof Error ? err.message : "Feedback could not be saved.");
    }
  };

  const copy = async (message: UiMessage) => {
    try {
      await navigator.clipboard.writeText(textForClipboard(message.text, message.sources));
      toast.success("Answer copied with its citations.");
    } catch {
      toast.error("Copy is unavailable in this browser.");
    }
  };

  const showWow = async () => {
    try {
      const { discoveries } = await queryClient.fetchQuery({
        queryKey: ["discoveries"],
        queryFn: api.discoveries,
        staleTime: Number.POSITIVE_INFINITY,
      });
      if (discoveries.length === 0) {
        toast("Nothing to discover right now. Ask your own question instead.");
        return;
      }
      const discovery = discoveries[wowIndex.current % discoveries.length]!;
      wowIndex.current += 1;
      toast(discovery.title, {
        description: `${discovery.body}${discovery.citation ? ` — ${discovery.citation}` : ""}`,
        duration: 8000,
      });
      void send(discovery.question, []);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Discoveries are unavailable right now.");
    }
  };

  const onComposerError = useCallback(({ code, message }: { code: string; message: string }) => {
    toast.error(
      code === "max_file_size" || code === "accept"
        ? UPLOAD_TYPE_MESSAGE
        : code === "max_files"
          ? "You can attach up to 5 documents at a time."
          : message,
    );
  }, []);

  const status: ComposerStatus =
    phase === "streaming" ? "streaming" : phase === "idle" ? "ready" : "submitted";
  const title =
    conversations.find((c) => c.id === threadId)?.title ?? detail.data?.title ?? "New conversation";
  const loadingThread = !!threadId && detail.isPending && messages.length === 0;
  const showWelcome = messages.length === 0 && !loadingThread && !notFound && !detail.isError;
  const lastAssistantId = useMemo(
    () => [...messages].reverse().find((m) => m.role === "assistant")?.id,
    [messages],
  );
  const openSource = useCallback((ref: SourceRef) => setSource(ref), []);

  return (
    <ChatShell
      threadId={threadId}
      mobileOpen={mobileOpen}
      closeMobile={() => setMobileOpen(false)}
      source={source}
      closeSource={() => setSource(null)}
      businesses={<BusinessPicker selectedId={scope.businessId} onSelect={scope.selectBusiness} />}
    >
      <main className={`chat-stage ${showWelcome ? "empty-chat" : ""}`}>
        <header className="stage-header">
          <div className="flex items-center gap-2">
            <Button
              id="navigation-toggle"
              className="navigation-toggle"
              aria-expanded={mobileOpen}
              variant="ghost"
              size="icon-sm"
              aria-label={mobileOpen ? "Hide navigation" : "Show navigation"}
              title={mobileOpen ? "Hide navigation" : "Show navigation"}
              onClick={() => setMobileOpen((open) => !open)}
            >
              <Menu />
            </Button>
            <span className="stage-header-title">
              <span className="header-workspace">Workspace</span>
              <span className="header-divider">/</span>
              <span className="header-context">{title}</span>
            </span>
          </div>
          <div className="flex items-center gap-2">
            {!mobileOpen && <ThemeMenu />}
            <Button asChild variant="ghost" size="sm" className="header-plan">
              <Link to="/billing">
                Explore plans <ArrowUpRight className="size-3" />
              </Link>
            </Button>
          </div>
        </header>
        <div className="chat-content">
          {loadingThread ? (
            <div className="m-auto text-sm text-muted-foreground">
              <Shimmer>Opening your conversation…</Shimmer>
            </div>
          ) : notFound ? (
            <div className="m-auto px-8 text-center">
              <h1 className="text-2xl">Conversation not found</h1>
              <p className="text-sm text-muted-foreground mt-3">
                It may have been deleted. Your other conversations are in the sidebar.
              </p>
              <Button asChild className="mt-6">
                <Link to="/">Start a conversation</Link>
              </Button>
            </div>
          ) : detail.isError && messages.length === 0 ? (
            <div className="m-auto px-8 text-center">
              <h1 className="text-2xl">This conversation didn't load</h1>
              <p className="text-sm text-muted-foreground mt-3">{detail.error.message}</p>
              <Button className="mt-6" onClick={() => void detail.refetch()}>
                Try again
              </Button>
            </div>
          ) : showWelcome ? (
            <ChatWelcome mode={scope.mode} onModeChange={scope.setMode} business={business} />
          ) : (
            <Conversation
              className="transcript"
              aria-label="Conversation messages"
              initial={reduced ? "instant" : "smooth"}
              resize={reduced ? "instant" : "smooth"}
            >
              <ConversationContent className="transcript-content">
                {messages.map((m) =>
                  m.role === "user" ? (
                    <UserMessage key={m.id} message={m} />
                  ) : (
                    <AssistantMessage
                      key={m.id}
                      message={m}
                      canRegenerate={phase === "idle" && m.id === lastAssistantId && !!threadId}
                      openSource={openSource}
                      onCopy={(message) => void copy(message)}
                      onFeedback={(message, rating) => void feedback(message, rating)}
                      onRegenerate={regenerate}
                    />
                  ),
                )}
              </ConversationContent>
              <ConversationScrollButton aria-label="Scroll to latest message" />
            </Conversation>
          )}
        </div>
        <div className="composer-area">
          <div className="chat-width">
            {!notFound && !detail.isError && messages.length === 0 && (
              <PromptSuggestions
                mode={scope.mode}
                choosePrompt={(text) => void send(text, [])}
                disabled={status !== "ready"}
              />
            )}
            {activeBusinessId && business && (
              <ScopeChip business={business} onClear={() => scope.setMode("personal")} />
            )}
            <UploadProgress items={uploads.items} />
            <PromptInput
              className="singlaw-composer"
              onSubmit={({ text, files }) => {
                void send(text, files);
              }}
              multiple
              maxFiles={5}
              maxFileSize={MAX_UPLOAD_BYTES}
              onError={onComposerError}
            >
              <Attachments />
              <PromptInputTextarea
                ref={textarea}
                aria-label="Ask SingLaw"
                placeholder={
                  messages.length
                    ? "Ask a follow-up question…"
                    : "What would you like to understand?"
                }
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={notFound || detail.isError}
              />
              <PromptInputFooter>
                <div className="flex items-center gap-1">
                  <UploadButton
                    onError={(message) => toast.error(message)}
                    disabled={status !== "ready"}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    className="wow-button"
                    type="button"
                    onClick={() => void showWow()}
                    disabled={status !== "ready" || notFound}
                    title="Discover a surprising side of Singapore law"
                  >
                    <Sparkles className="size-3" /> Wow Me!
                  </Button>
                </div>
                <span className="composer-hint">
                  <kbd>Enter</kbd> to send · <kbd>Shift + Enter</kbd> for a new line
                </span>
                <ComposerSubmit
                  status={status}
                  stop={stopStream}
                  hasText={!!input.trim() && !notFound}
                />
              </PromptInputFooter>
            </PromptInput>
            <p className="composer-disclaimer">
              {DISCLAIMER_TEXT} <Link to="/terms">Terms & privacy</Link>
            </p>
            {showWelcome && <WorkspaceSources />}
          </div>
        </div>
      </main>
    </ChatShell>
  );
}
