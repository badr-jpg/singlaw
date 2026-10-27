import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Store,
  Utensils,
  Briefcase,
  Factory,
  Laptop,
  HeartPulse,
  Truck,
  Settings,
  Plus,
  FileText,
  Trash2,
  Upload,
  X,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Spinner } from "@/components/ui/spinner";
import { api, ApiError, type Business, type UploadedDocument } from "@/lib/api";
import { UPLOAD_ACCEPT, UPLOAD_TYPE_MESSAGE, isAllowedUpload } from "@/lib/singlaw";
import { MetaChip } from "./trust/badges";

export const BUSINESSES_KEY = ["businesses"] as const;

const icons = { Building2, Store, Utensils, Briefcase, Factory, Laptop, HeartPulse, Truck };
type IconName = keyof typeof icons;

function iconFor(name: string) {
  return (icons as Record<string, typeof Building2>)[name] ?? Building2;
}

type DialogState = { mode: "create" } | { mode: "edit"; id: string } | null;

export function BusinessPicker({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const list = useQuery({
    queryKey: BUSINESSES_KEY,
    queryFn: api.listBusinesses,
    staleTime: 60_000,
  });
  const [dialog, setDialog] = useState<DialogState>(null);
  const items = useMemo(() => list.data ?? [], [list.data]);

  // A stored selection that no longer exists on the server is dropped.
  useEffect(() => {
    if (list.isSuccess && selectedId && !items.some((b) => b.id === selectedId)) onSelect(null);
  }, [list.isSuccess, items, selectedId, onSelect]);

  if (list.isPending) return null;

  return (
    <div className="business-picker enter">
      <div className="business-picker-head">
        <span>Your businesses</span>
        <span className="text-muted-foreground">{items.length || ""}</span>
      </div>
      {list.isError ? (
        <button
          type="button"
          className="business-item business-add"
          onClick={() => void list.refetch()}
        >
          <RefreshCw className="size-4" /> Businesses unavailable — retry
        </button>
      ) : (
        <div className="business-list">
          {items.map((b) => {
            const Icon = iconFor(b.icon);
            return (
              <div key={b.id} className="business-item" data-active={b.id === selectedId}>
                <button
                  type="button"
                  className="business-select"
                  onClick={() => onSelect(b.id === selectedId ? null : b.id)}
                  aria-pressed={b.id === selectedId}
                >
                  <span className="business-icon">
                    <Icon className="size-4" />
                  </span>
                  <span className="min-w-0 text-left">
                    <span className="block truncate font-medium">{b.name}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {b.document_count} document{b.document_count === 1 ? "" : "s"}
                    </span>
                  </span>
                </button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="rounded-full size-8 shrink-0"
                  aria-label={`Settings for ${b.name}`}
                  onClick={() => setDialog({ mode: "edit", id: b.id })}
                >
                  <Settings className="size-4" />
                </Button>
              </div>
            );
          })}
          <button
            type="button"
            className="business-item business-add"
            onClick={() => setDialog({ mode: "create" })}
          >
            <Plus className="size-4" /> Add a business
          </button>
        </div>
      )}
      <BusinessDialog
        state={dialog}
        business={dialog?.mode === "edit" ? (items.find((b) => b.id === dialog.id) ?? null) : null}
        onChange={setDialog}
        onCreated={(b) => onSelect(b.id)}
        onDeleted={(id) => {
          if (selectedId === id) onSelect(null);
        }}
      />
    </div>
  );
}

function BusinessDialog({
  state,
  business,
  onChange,
  onCreated,
  onDeleted,
}: {
  state: DialogState;
  business: Business | null;
  onChange: (state: DialogState) => void;
  onCreated: (business: Business) => void;
  onDeleted: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [icon, setIcon] = useState<IconName>("Building2");
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const open = !!state;

  useEffect(() => {
    if (!state) return;
    if (state.mode === "edit" && business) {
      setName(business.name);
      setDescription(business.description);
      setIcon((business.icon in icons ? business.icon : "Building2") as IconName);
    } else if (state.mode === "create") {
      setName("");
      setDescription("");
      setIcon("Building2");
    }
    setConfirmDelete(false);
  }, [state?.mode, state?.mode === "edit" ? state.id : null, business?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const close = () => onChange(null);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: BUSINESSES_KEY });

  const save = async () => {
    const trimmed = name.trim();
    if (!trimmed || !state) return;
    setSaving(true);
    try {
      if (state.mode === "create") {
        const created = await api.createBusiness({
          name: trimmed,
          description: description.trim(),
          icon,
        });
        await invalidate();
        onCreated(created);
        toast.success(`${created.name} added. Upload its documents to bring them into answers.`);
        onChange({ mode: "edit", id: created.id });
      } else {
        await api.updateBusiness(state.id, {
          name: trimmed,
          description: description.trim(),
          icon,
        });
        await invalidate();
        close();
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) toast.error(err.message);
      else toast.error(err instanceof Error ? err.message : "The business could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!state || state.mode !== "edit") return;
    setSaving(true);
    try {
      await api.deleteBusiness(state.id);
      queryClient.removeQueries({ queryKey: ["business-docs", state.id] });
      await invalidate();
      onDeleted(state.id);
      setConfirmDelete(false);
      close();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "The business could not be deleted.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && close()}>
        {state && (
          <DialogContent className="business-dialog sm:max-w-lg rounded-3xl">
            <DialogHeader>
              <DialogTitle>
                {state.mode === "create" ? "Add a business" : "Business settings"}
              </DialogTitle>
              <DialogDescription>
                Describe your business so answers can take its context into account. Documents you
                add are searched alongside Singapore law.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4">
              <div className="grid gap-2">
                <Label>Icon</Label>
                <div className="flex flex-wrap gap-2">
                  {(Object.keys(icons) as IconName[]).map((n) => {
                    const I = icons[n];
                    return (
                      <button
                        key={n}
                        type="button"
                        aria-label={n}
                        data-active={icon === n}
                        aria-pressed={icon === n}
                        className="business-icon-choice"
                        onClick={() => setIcon(n)}
                      >
                        <I className="size-4" />
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="biz-name">Name</Label>
                <Input
                  id="biz-name"
                  className="rounded-xl"
                  value={name}
                  maxLength={60}
                  placeholder="e.g. Tanjong Bakery Pte Ltd"
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="biz-desc">Description</Label>
                <Textarea
                  id="biz-desc"
                  className="rounded-xl"
                  rows={3}
                  maxLength={400}
                  placeholder="e.g. F&B outlet in Tampines with 12 staff"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
              {state.mode === "edit" ? (
                <BusinessDocuments businessId={state.id} />
              ) : (
                <p className="text-xs text-muted-foreground">
                  Save the business first, then add contracts, policies or handbooks for it.
                </p>
              )}
            </div>
            <DialogFooter className="sm:justify-between gap-2">
              {state.mode === "edit" ? (
                <Button
                  variant="ghost"
                  className="rounded-full text-destructive"
                  disabled={saving}
                  onClick={() => setConfirmDelete(true)}
                >
                  <Trash2 className="size-4" /> Delete
                </Button>
              ) : (
                <span />
              )}
              <Button
                className="rounded-full"
                disabled={!name.trim() || saving}
                onClick={() => void save()}
              >
                {saving ? <Spinner /> : null}
                {state.mode === "create" ? "Create business" : "Save changes"}
              </Button>
            </DialogFooter>
          </DialogContent>
        )}
      </Dialog>
      <AlertDialog open={confirmDelete} onOpenChange={(o) => !saving && setConfirmDelete(o)}>
        <AlertDialogContent className="singlaw-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {business?.name ?? "this business"}?</AlertDialogTitle>
            <AlertDialogDescription>
              The business and {business?.document_count ?? 0} uploaded document
              {business?.document_count === 1 ? "" : "s"} will be deleted. Conversations that used
              them stay, but new answers will no longer draw on these documents.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={saving}>Keep it</AlertDialogCancel>
            <AlertDialogAction
              className="confirm-destructive"
              disabled={saving}
              onClick={(event) => {
                event.preventDefault();
                void remove();
              }}
            >
              {saving ? "Deleting…" : "Delete business"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function statusTone(status: UploadedDocument["status"]) {
  return status === "ready" ? "positive" : status === "error" ? "danger" : "caution";
}

function BusinessDocuments({ businessId }: { businessId: string }) {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(0);
  const docs = useQuery({
    queryKey: ["business-docs", businessId],
    queryFn: () => api.listBusinessDocuments(businessId),
    refetchInterval: (query) =>
      query.state.data?.some((d) => d.status === "pending" || d.status === "processing")
        ? 1500
        : false,
  });
  const items = docs.data ?? [];

  const refreshAll = async () => {
    await queryClient.invalidateQueries({ queryKey: ["business-docs", businessId] });
    await queryClient.invalidateQueries({ queryKey: BUSINESSES_KEY });
  };

  const upload = async (files: File[]) => {
    const allowed = files.filter((f) => isAllowedUpload(f.name, f.size));
    if (allowed.length !== files.length) toast.error(UPLOAD_TYPE_MESSAGE);
    if (allowed.length === 0) return;
    setUploading((n) => n + allowed.length);
    await Promise.all(
      allowed.map(async (file) => {
        try {
          await api.uploadDocument(file, businessId);
        } catch (err) {
          toast.error(`${file.name}: ${err instanceof Error ? err.message : "upload failed"}`);
        } finally {
          setUploading((n) => n - 1);
        }
      }),
    );
    await refreshAll();
  };

  const remove = async (doc: UploadedDocument) => {
    try {
      await api.deleteDocument(doc.id);
      await refreshAll();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "The document could not be removed.");
    }
  };

  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between">
        <Label>Documents</Label>
        <Button
          variant="outline"
          size="sm"
          className="rounded-full"
          disabled={uploading > 0}
          onClick={() => fileRef.current?.click()}
        >
          {uploading > 0 ? <Spinner /> : <Upload className="size-3" />} Add documents
        </Button>
        <input
          ref={fileRef}
          type="file"
          multiple
          hidden
          accept={UPLOAD_ACCEPT}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            void upload(files);
          }}
        />
      </div>
      {docs.isPending ? (
        <p className="text-xs text-muted-foreground">Loading documents…</p>
      ) : docs.isError ? (
        <p className="text-xs text-destructive">{docs.error.message}</p>
      ) : items.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No documents yet. Add contracts, policies or handbooks (PDF, Word, text or Markdown).
        </p>
      ) : (
        <ul className="grid gap-1.5">
          {items.map((d) => (
            <li key={d.id} className="business-doc" data-status={d.status}>
              <FileText className="size-3.5 shrink-0" />
              <span className="min-w-0 flex-1">
                <span className="block truncate">{d.filename}</span>
                {d.status === "error" && d.error && (
                  <span className="block truncate text-xs text-danger">{d.error}</span>
                )}
              </span>
              <MetaChip tone={statusTone(d.status)}>
                {d.status === "ready"
                  ? `${d.chunk_count} chunk${d.chunk_count === 1 ? "" : "s"}`
                  : d.status === "error"
                    ? "Error"
                    : d.status === "processing"
                      ? "Processing…"
                      : "Queued"}
              </MetaChip>
              <button
                type="button"
                aria-label={`Remove ${d.filename}`}
                onClick={() => void remove(d)}
              >
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
