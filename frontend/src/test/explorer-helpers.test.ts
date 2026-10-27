import { describe, expect, it } from "vitest";
import type { DocTreeNode } from "@/lib/api";
import {
  ancestorKeys,
  askAboutUrl,
  corpusSummary,
  docIdFromChunkId,
  docTypeLabel,
  firstLeaf,
  flattenLeaves,
  formatDate,
  isFlagged,
  neighbourLeaves,
  normaliseScore,
  scorePercent,
  statusLabel,
  statusTone,
  tierLabel,
  tierName,
  treatmentLabel,
  treatmentTone,
} from "@/components/singlaw/explorer/helpers";

const leaf = (label: string, chunk_id: string): DocTreeNode => ({
  label,
  citation: null,
  chunk_id,
  children: [],
});
const group = (label: string, children: DocTreeNode[]): DocTreeNode => ({
  label,
  citation: null,
  chunk_id: null,
  children,
});
const tree: DocTreeNode[] = [
  group("Part 1 — Preliminary", [
    leaf("Section 1 — Short title", "ea:s1"),
    leaf("Section 2", "ea:s2"),
  ]),
  group("Part 2 — Contracts", [
    group("Division 1 — Termination", [leaf("Section 14 — Misconduct", "ea:s14")]),
  ]),
];

describe("Explorer helpers", () => {
  it("derives the document id from a chunk id", () => {
    expect(docIdFromChunkId("employment-act-1968:s14")).toBe("employment-act-1968");
    expect(docIdFromChunkId("2022-sgca-60-foo-v-bar:para1-20")).toBe("2022-sgca-60-foo-v-bar");
    expect(docIdFromChunkId("no-colon")).toBe("no-colon");
  });

  it("names authority tiers 1–6 and tolerates unknown tiers", () => {
    expect(tierName(1)).toBe("Constitution");
    expect(tierName(2)).toBe("Act");
    expect(tierName(3)).toBe("Subsidiary legislation");
    expect(tierName(4)).toBe("Binding judgment");
    expect(tierName(5)).toBe("Lower court");
    expect(tierName(6)).toBe("Guidance");
    expect(tierLabel(2)).toBe("Tier 2 · Act");
    expect(tierName(9)).toBe("Unranked");
    expect(tierName(null)).toBe("Unranked");
  });

  it("flags repealed in red and hides a blank status", () => {
    expect(statusLabel("in_force")).toBe("In force");
    expect(statusTone("in_force")).toBe("ok");
    expect(statusLabel("repealed")).toBe("Repealed");
    expect(statusTone("repealed")).toBe("danger");
    expect(statusTone("not_yet_commenced")).toBe("caution");
    expect(statusLabel("n_a")).toBe("");
    expect(docTypeLabel("practice_direction")).toBe("Practice direction");
  });

  it("renders treatment only when it carries a signal", () => {
    expect(treatmentLabel("overruled")).toBe("Overruled");
    expect(treatmentTone("overruled")).toBe("danger");
    expect(treatmentLabel("distinguished")).toBe("Distinguished");
    expect(treatmentTone("distinguished")).toBe("caution");
    expect(treatmentLabel("good")).toBe("Good law");
    expect(treatmentLabel("unknown")).toBeNull();
    expect(isFlagged("repealed", "unknown")).toBe(true);
    expect(isFlagged("in_force", "overruled")).toBe(true);
    expect(isFlagged("in_force", "good")).toBe(false);
  });

  it("walks the document tree", () => {
    expect(flattenLeaves(tree).map((n) => n.chunk_id)).toEqual(["ea:s1", "ea:s2", "ea:s14"]);
    expect(firstLeaf(tree)?.chunk_id).toBe("ea:s1");
    expect(ancestorKeys(tree, "ea:s14")).toEqual(["1", "1.0"]);
    expect(ancestorKeys(tree, "missing")).toEqual([]);
    expect(neighbourLeaves(tree, "ea:s2")).toEqual({
      previous: expect.objectContaining({ chunk_id: "ea:s1" }),
      next: expect.objectContaining({ chunk_id: "ea:s14" }),
    });
    expect(neighbourLeaves(tree, "ea:s14").next).toBeNull();
  });

  it("formats dates, counts and scores", () => {
    expect(formatDate("2026-10-07")).toBe("7 Oct 2026");
    expect(formatDate(null)).toBeNull();
    expect(formatDate("not a date")).toBe("not a date");
    expect(
      corpusSummary({
        corpus: {
          acts: 412,
          subsidiary_legislation: 1208,
          judgments: 1,
          practice_directions: 12,
          repealed: 3,
        },
        last_sync: "2026-10-07T05:30:00+08:00",
      }),
    ).toBe(
      "412 Acts · 1,208 subsidiary legislation · 1 judgment · 12 practice directions · synced 7 Oct 2026",
    );
    expect(
      corpusSummary({
        corpus: {
          acts: 0,
          subsidiary_legislation: 0,
          judgments: 0,
          practice_directions: 0,
          repealed: 0,
        },
        last_sync: null,
      }),
    ).toContain("not synced yet");
    expect(scorePercent(0.834)).toBe(83);
    expect(scorePercent(1.7)).toBe(100);
    expect(normaliseScore(0.4)).toBe(0.4);
    expect(normaliseScore(4)).toBeGreaterThan(0.9);
    expect(normaliseScore(-4)).toBeLessThan(0.1);
  });

  it("hands a provision to the chat workspace through ?q=", () => {
    expect(askAboutUrl("Employment Act 1968, s 14")).toBe(
      "/?q=What%20does%20Employment%20Act%201968%2C%20s%2014%20say%3F",
    );
  });
});
