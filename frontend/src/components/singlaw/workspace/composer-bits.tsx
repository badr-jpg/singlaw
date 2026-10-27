import { useRef } from "react";
import { ArrowUp, Building2, Check, FileText, Paperclip, X, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { PromptInputSubmit } from "@/components/ai-elements/prompt-input";
import { usePromptInputAttachments } from "@/components/ai-elements/prompt-input-context";
import type { Business } from "@/lib/api";
import { UPLOAD_ACCEPT, UPLOAD_TYPE_MESSAGE, isAllowedUpload } from "@/lib/singlaw";
import type { UploadItem } from "@/hooks/use-document-uploads";

export type ComposerStatus = "ready" | "submitted" | "streaming";

/** Files waiting in the composer, before they are sent. */
export function Attachments() {
  const attachments = usePromptInputAttachments();
  if (attachments.files.length === 0) return null;
  return (
    <div className="composer-chips" aria-label="Documents to analyse">
      {attachments.files.map((file) => (
        <span className="attachment-chip" key={file.id}>
          <FileText size={12} aria-hidden="true" />
          <span className="truncate max-w-40">{file.filename}</span>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={`Remove ${file.filename}`}
            onClick={() => attachments.remove(file.id)}
          >
            <X size={11} />
          </Button>
        </span>
      ))}
    </div>
  );
}

/** Per-file progress while documents upload and are processed. */
export function UploadProgress({ items }: { items: UploadItem[] }) {
  if (items.length === 0) return null;
  return (
    <div className="composer-chips upload-progress" role="status" aria-live="polite">
      <span className="upload-progress-label">Preparing documents</span>
      {items.map((item) => (
        <span
          className="attachment-chip"
          data-status={item.status}
          key={item.key}
          title={item.error}
        >
          {item.status === "ready" ? (
            <Check size={12} aria-hidden="true" />
          ) : item.status === "error" ? (
            <AlertCircle size={12} aria-hidden="true" />
          ) : (
            <Spinner className="size-3" />
          )}
          <span className="truncate max-w-40">{item.filename}</span>
          <span className="upload-state">
            {item.status === "uploading"
              ? "uploading"
              : item.status === "ready"
                ? "ready"
                : item.status === "error"
                  ? "failed"
                  : item.status === "processing"
                    ? "reading"
                    : "queued"}
          </span>
        </span>
      ))}
    </div>
  );
}

export function ComposerSubmit({
  status,
  stop,
  hasText,
}: {
  status: ComposerStatus;
  stop: () => void;
  hasText: boolean;
}) {
  const attachments = usePromptInputAttachments();
  return (
    <PromptInputSubmit
      status={status}
      onStop={stop}
      disabled={status === "ready" && !hasText && attachments.files.length === 0}
      title={status === "ready" ? "Ask SingLaw" : "Stop response"}
      aria-label={status === "ready" ? "Send message" : "Stop response"}
    >
      {status === "ready" ? <ArrowUp /> : undefined}
    </PromptInputSubmit>
  );
}

/**
 * Attach button with its own file input so the native dialog filters by
 * extension; the PromptInput's MIME-based `accept` cannot express ".md".
 */
export function UploadButton({
  onError,
  disabled,
}: {
  onError: (message: string) => void;
  disabled?: boolean;
}) {
  const attachments = usePromptInputAttachments();
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        accept={UPLOAD_ACCEPT}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          event.target.value = "";
          const allowed = files.filter((f) => isAllowedUpload(f.name, f.size));
          if (allowed.length !== files.length) onError(UPLOAD_TYPE_MESSAGE);
          if (allowed.length > 0) attachments.add(allowed);
        }}
      />
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="rounded-full"
        aria-label="Attach a document to analyse"
        title="Attach a document (PDF, Word, text or Markdown, up to 25 MB)"
        disabled={disabled}
        onClick={() => input.current?.click()}
      >
        <Paperclip />
      </Button>
    </>
  );
}

/** "Scoped to {business} · n documents" above the composer. */
export function ScopeChip({ business, onClear }: { business: Business; onClear: () => void }) {
  return (
    <div className="scope-chip" role="status">
      <Building2 size={12} aria-hidden="true" />
      <span>
        Scoped to <strong>{business.name}</strong> · {business.document_count} document
        {business.document_count === 1 ? "" : "s"}
      </span>
      <Button
        variant="ghost"
        size="icon-xs"
        aria-label={`Stop scoping answers to ${business.name}`}
        title="Ask without business scope"
        onClick={onClear}
      >
        <X size={11} />
      </Button>
    </div>
  );
}
