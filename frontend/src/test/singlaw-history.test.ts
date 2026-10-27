import { describe, expect, it } from "vitest";
import type { ChatMeta, ConversationMessage, ConversationSummary, Source } from "@/lib/api";
import { fromServerMessage, groupConversations, messagesFromConversation } from "@/lib/singlaw";

const source: Source = {
  n: 1,
  chunk_id: "c1",
  citation: "Employment Act 1968, s 14",
  url: "https://sso.agc.gov.sg/Act/EmA1968",
  doc_type: "act",
  authority_tier: 2,
  status: "in_force",
  treatment: "none",
  court: null,
  decision_date: null,
  hierarchy_path: ["Employment Act 1968", "Part 4", "s 14"],
  snippet: "…",
  collection: "sg_law",
};

const meta: ChatMeta = {
  conversation_id: "conv",
  message_id: "m2",
  intent: "statutory_lookup",
  low_confidence: false,
  filtered: { repealed: 0, spent: 0, not_yet_commenced: 0 },
  temporal_basis: "2026-10-07",
  high_stakes: { triggered: false, reasons: [], referrals: [] },
  attribution: "© Singapore Government",
  disclaimer: "Legal information, not legal advice.",
  corpus_last_synced: null,
};

describe("Server messages → UI messages", () => {
  it("keeps the server id for feedback and lifts validation out of meta", () => {
    const stored: ConversationMessage = {
      id: "m2",
      role: "assistant",
      content: "Notice is required. [CITE:1]",
      created_at: "2026-10-07T01:00:00Z",
      sources: [source],
      meta: {
        ...meta,
        validation: { grounded: true, unsupported_sentences: [], invalid_cites: [] },
      },
      feedback: "up",
    };
    const ui = fromServerMessage(stored, "How much notice?");
    expect(ui.serverId).toBe("m2");
    expect(ui.text).toBe("Notice is required. [CITE:1]");
    expect(ui.sources).toEqual([source]);
    expect(ui.meta?.temporal_basis).toBe("2026-10-07");
    expect(ui.meta && "validation" in ui.meta).toBe(false);
    expect(ui.validation?.grounded).toBe(true);
    expect(ui.feedback).toBe("up");
    expect(ui.question).toBe("How much notice?");
    expect(ui.streaming).toBeUndefined();
  });

  it("treats an empty meta object as no meta", () => {
    const ui = fromServerMessage({
      id: "m1",
      role: "user",
      content: "Hi",
      created_at: "2026-10-07T00:59:00Z",
      sources: [],
      meta: {},
    });
    expect(ui.meta).toBeUndefined();
    expect(ui.validation).toBeUndefined();
    expect(ui.feedback).toBeNull();
    expect(ui.question).toBeUndefined();
  });

  it("pairs each answer with the question that preceded it", () => {
    const ui = messagesFromConversation({
      messages: [
        { id: "u1", role: "user", content: "First?", created_at: "t", sources: [], meta: {} },
        { id: "a1", role: "assistant", content: "One.", created_at: "t", sources: [], meta },
        { id: "u2", role: "user", content: "Second?", created_at: "t", sources: [], meta: {} },
        { id: "a2", role: "assistant", content: "Two.", created_at: "t", sources: [], meta },
      ],
    });
    expect(ui.map((m) => m.question)).toEqual([undefined, "First?", undefined, "Second?"]);
  });
});

describe("Sidebar grouping", () => {
  const now = new Date("2026-10-07T12:00:00+08:00");
  const summary = (id: string, updated_at: string): ConversationSummary => ({
    id,
    title: id,
    created_at: updated_at,
    updated_at,
    message_count: 2,
  });

  it("buckets by updated_at into Today, Previous 7 days and Older, newest first", () => {
    const groups = groupConversations(
      [
        summary("old", "2026-09-01T10:00:00+08:00"),
        summary("today-early", "2026-10-07T01:00:00+08:00"),
        summary("week", "2026-10-03T10:00:00+08:00"),
        summary("today-late", "2026-10-07T11:00:00+08:00"),
      ],
      now,
    );
    expect(groups.map((g) => g.label)).toEqual(["Today", "Previous 7 days", "Older"]);
    expect(groups[0]?.items.map((c) => c.id)).toEqual(["today-late", "today-early"]);
    expect(groups[1]?.items.map((c) => c.id)).toEqual(["week"]);
    expect(groups[2]?.items.map((c) => c.id)).toEqual(["old"]);
  });

  it("omits empty buckets and tolerates unparseable dates", () => {
    const groups = groupConversations([summary("odd", "not-a-date")], now);
    expect(groups).toEqual([{ label: "Older", items: [summary("odd", "not-a-date")] }]);
    expect(groupConversations([], now)).toEqual([]);
  });
});
