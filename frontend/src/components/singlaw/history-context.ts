import { createContext, useContext } from "react";
import type { ConversationSummary } from "@/lib/api";
import type { MessageAttachment } from "@/lib/singlaw";

/** A question captured on `/` and answered once its new conversation page mounts. */
export interface PendingQuestion {
  question: string;
  docIds: string[] | null;
  businessId: string | null;
  attachments: MessageAttachment[];
}

export interface HistoryState {
  conversations: ConversationSummary[];
  /** True once the first list request has settled (successfully or not). */
  ready: boolean;
  error: string;
  create: (title: string) => Promise<ConversationSummary>;
  rename: (id: string, title: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  refresh: () => void;
  stashPending: (id: string, pending: PendingQuestion) => void;
  takePending: (id: string) => PendingQuestion | null;
}

// Keep context identity outside the component's Fast Refresh boundary.
export const HistoryContext = createContext<HistoryState | null>(null);

export function useHistory() {
  const context = useContext(HistoryContext);
  if (!context) throw new Error("HistoryProvider is required");
  return context;
}
