import { useCallback, useEffect, useRef, useState } from "react";
import { api, type DocumentStatus } from "@/lib/api";
import type { MessageAttachment } from "@/lib/singlaw";

export interface UploadItem {
  key: string;
  filename: string;
  status: "uploading" | DocumentStatus;
  id?: string | undefined;
  error?: string | undefined;
}

export interface UploadOutcome {
  ready: MessageAttachment[];
  failed: { filename: string; error: string }[];
}

const POLL_MS = 1500;
const DEADLINE_MS = 5 * 60 * 1000;

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Uploads files, then polls the document list until each is `ready` (or
 * `error`). Progress is exposed as chips while the composer waits.
 */
export function useDocumentUploads() {
  const [items, setItems] = useState<UploadItem[]>([]);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const patch = useCallback((key: string, change: Partial<UploadItem>) => {
    if (!mounted.current) return;
    setItems((all) => all.map((item) => (item.key === key ? { ...item, ...change } : item)));
  }, []);

  const uploadAll = useCallback(
    async (files: File[], businessId: string | null): Promise<UploadOutcome> => {
      const tracked: UploadItem[] = files.map((file, i) => ({
        key: `${Date.now()}-${i}-${file.name}`,
        filename: file.name,
        status: "uploading",
      }));
      setItems(tracked);

      await Promise.all(
        files.map(async (file, i) => {
          const item = tracked[i]!;
          try {
            const res = await api.uploadDocument(file, businessId ?? undefined);
            item.id = res.id;
            item.status = "pending";
            patch(item.key, { id: res.id, status: "pending" });
          } catch (err) {
            item.status = "error";
            item.error = err instanceof Error ? err.message : "Upload failed.";
            patch(item.key, { status: "error", error: item.error });
          }
        }),
      );

      const started = Date.now();
      const unfinished = () =>
        tracked.filter((t) => t.id && (t.status === "pending" || t.status === "processing"));
      while (unfinished().length > 0) {
        if (Date.now() - started > DEADLINE_MS) {
          for (const t of unfinished()) {
            t.status = "error";
            t.error = "Processing took too long. Try again later.";
            patch(t.key, { status: "error", error: t.error });
          }
          break;
        }
        await sleep(POLL_MS);
        let docs;
        try {
          docs = await api.listDocuments();
        } catch {
          continue;
        }
        for (const t of unfinished()) {
          const doc = docs.find((d) => d.id === t.id);
          if (!doc) continue;
          if (doc.status === "error") {
            t.status = "error";
            t.error = doc.error || "This document could not be processed.";
            patch(t.key, { status: "error", error: t.error });
          } else if (doc.status !== t.status) {
            t.status = doc.status;
            patch(t.key, { status: doc.status });
          }
        }
      }

      return {
        ready: tracked
          .filter((t): t is UploadItem & { id: string } => t.status === "ready" && !!t.id)
          .map((t) => ({ id: t.id, filename: t.filename })),
        failed: tracked
          .filter((t) => t.status === "error")
          .map((t) => ({ filename: t.filename, error: t.error ?? "Upload failed." })),
      };
    },
    [patch],
  );

  const reset = useCallback(() => setItems([]), []);

  return { items, uploadAll, reset };
}
