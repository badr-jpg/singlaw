import { useCallback, useMemo, useRef, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ConversationSummary } from "@/lib/api";
import { HistoryContext, type HistoryState, type PendingQuestion } from "./history-context";

export const CONVERSATIONS_KEY = ["conversations"] as const;

/** Thin React Query layer over the server's conversation list. */
export function HistoryProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const list = useQuery({
    queryKey: CONVERSATIONS_KEY,
    queryFn: api.listConversations,
    staleTime: 30_000,
  });
  const pending = useRef(new Map<string, PendingQuestion>());

  const setList = useCallback(
    (fn: (all: ConversationSummary[]) => ConversationSummary[]) =>
      queryClient.setQueryData<ConversationSummary[]>(CONVERSATIONS_KEY, (old) => fn(old ?? [])),
    [queryClient],
  );

  const refresh = useCallback(
    () => void queryClient.invalidateQueries({ queryKey: CONVERSATIONS_KEY }),
    [queryClient],
  );

  const create = useCallback(
    async (title: string) => {
      const created = await api.createConversation(title.trim() || undefined);
      setList((all) => [created, ...all.filter((c) => c.id !== created.id)]);
      return created;
    },
    [setList],
  );

  const rename = useCallback(
    async (id: string, title: string) => {
      const previous = queryClient.getQueryData<ConversationSummary[]>(CONVERSATIONS_KEY);
      setList((all) => all.map((c) => (c.id === id ? { ...c, title } : c)));
      try {
        await api.renameConversation(id, title);
      } catch (err) {
        if (previous) queryClient.setQueryData(CONVERSATIONS_KEY, previous);
        throw err;
      } finally {
        refresh();
      }
    },
    [queryClient, refresh, setList],
  );

  const remove = useCallback(
    async (id: string) => {
      await api.deleteConversation(id);
      setList((all) => all.filter((c) => c.id !== id));
      queryClient.removeQueries({ queryKey: ["conversation", id] });
      pending.current.delete(id);
    },
    [queryClient, setList],
  );

  const stashPending = useCallback((id: string, p: PendingQuestion) => {
    pending.current.set(id, p);
  }, []);

  const takePending = useCallback((id: string) => {
    const p = pending.current.get(id) ?? null;
    pending.current.delete(id);
    return p;
  }, []);

  const value = useMemo<HistoryState>(
    () => ({
      conversations: list.data ?? [],
      ready: !list.isPending,
      error: list.error ? list.error.message : "",
      create,
      rename,
      remove,
      refresh,
      stashPending,
      takePending,
    }),
    [
      list.data,
      list.isPending,
      list.error,
      create,
      rename,
      remove,
      refresh,
      stashPending,
      takePending,
    ],
  );

  return <HistoryContext.Provider value={value}>{children}</HistoryContext.Provider>;
}
