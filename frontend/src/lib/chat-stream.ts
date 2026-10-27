import { useCallback, useRef, useState } from "react";
import type {
  ChatMeta,
  ChatRequest,
  DoneEvent,
  ErrorEvent,
  SourcesEvent,
  TokenEvent,
  ValidationEvent,
} from "./api";

export interface ChatStreamHandlers {
  onMeta: (meta: ChatMeta) => void;
  onSources: (sources: SourcesEvent) => void;
  onToken: (token: TokenEvent) => void;
  onValidation: (validation: ValidationEvent) => void;
  onDone: (done: DoneEvent) => void;
  onError: (message: string) => void;
  onAbort: () => void;
}

/**
 * POST /api/chat as Server-Sent Events. EventSource cannot POST, so the fetch
 * body is read as a stream and SSE frames are parsed by hand: `event:` names
 * the event, `data:` lines carry JSON, a blank line terminates the frame.
 * Partial frames are buffered across network chunks; CRLF is tolerated.
 */
export async function streamChat(
  req: ChatRequest,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let eventName = "";
  let dataLines: string[] = [];
  let finished = false;

  const dispatch = (name: string, data: string) => {
    if (finished) return;
    let payload: unknown;
    try {
      payload = JSON.parse(data);
    } catch {
      handlers.onError("The server sent a malformed event.");
      return;
    }
    switch (name) {
      case "meta":
        handlers.onMeta(payload as ChatMeta);
        break;
      case "sources":
        handlers.onSources(payload as SourcesEvent);
        break;
      case "token":
        handlers.onToken(payload as TokenEvent);
        break;
      case "validation":
        handlers.onValidation(payload as ValidationEvent);
        break;
      case "done":
        finished = true;
        handlers.onDone(payload as DoneEvent);
        break;
      case "error":
        finished = true;
        handlers.onError((payload as ErrorEvent).message || "The server reported an error.");
        break;
      default:
        break;
    }
  };

  const processLine = (raw: string) => {
    const line = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
    if (line === "") {
      if (dataLines.length > 0) dispatch(eventName || "message", dataLines.join("\n"));
      eventName = "";
      dataLines = [];
      return;
    }
    if (line.startsWith(":")) return;
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) {
      let value = line.slice(5);
      if (value.startsWith(" ")) value = value.slice(1);
      dataLines.push(value);
    }
  };

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(req),
      signal: signal ?? null,
    });
    if (!res.ok) {
      let detail = "";
      try {
        const body: unknown = await res.json();
        const d = body && typeof body === "object" ? (body as Record<string, unknown>)["detail"] : "";
        if (typeof d === "string") detail = d;
      } catch {
        // ignore
      }
      handlers.onError(detail || `Chat request failed (${res.status} ${res.statusText})`);
      return;
    }
    if (!res.body) {
      handlers.onError("The server returned no response stream.");
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl = buffer.indexOf("\n");
      while (nl !== -1) {
        processLine(buffer.slice(0, nl));
        buffer = buffer.slice(nl + 1);
        nl = buffer.indexOf("\n");
      }
    }
    buffer += decoder.decode();
    if (buffer.length > 0) processLine(buffer);
    if (dataLines.length > 0) dispatch(eventName || "message", dataLines.join("\n"));
    if (!finished) handlers.onError("The stream ended before the answer completed.");
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") handlers.onAbort();
    else if (!finished) handlers.onError(err instanceof Error ? err.message : "Streaming failed.");
  }
}

/** React convenience around streamChat with an abortable in-flight request. */
export function useChatStream() {
  const abortRef = useRef<AbortController | null>(null);
  const [streaming, setStreaming] = useState(false);

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const send = useCallback(async (req: ChatRequest, handlers: ChatStreamHandlers) => {
    const controller = new AbortController();
    abortRef.current = controller;
    setStreaming(true);
    try {
      await streamChat(req, handlers, controller.signal);
    } finally {
      setStreaming(false);
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, []);

  return { streaming, send, stop };
}

/**
 * Citation markers in streamed text look like `[CITE:3]`. They are rewritten
 * to markdown links `[3](#cite-3)` so the markdown renderer can turn them into
 * citation chips. A marker cut off at the end of a chunk is held back.
 */
export function splitPendingCite(text: string): { renderable: string; held: string } {
  const open = text.lastIndexOf("[CITE:");
  if (open !== -1 && text.indexOf("]", open) === -1) {
    return { renderable: text.slice(0, open), held: text.slice(open) };
  }
  const tail = text.match(/\[(?:C(?:I(?:T(?:E)?)?)?)?$/);
  if (tail && tail.index !== undefined) {
    return { renderable: text.slice(0, tail.index), held: text.slice(tail.index) };
  }
  return { renderable: text, held: "" };
}

export function citeMarkersToLinks(text: string): string {
  return text.replace(/\[CITE:(\d+)\]/g, (_m, n: string) => `[${n}](#cite-${n})`);
}
