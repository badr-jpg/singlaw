import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Source } from "@/lib/api";
import {
  answerWarning,
  citeNumberFromHref,
  filteredSummary,
  lowConfidenceExplanation,
  renderableAnswer,
  textForClipboard,
} from "@/lib/singlaw";
import { AnswerContext } from "@/components/singlaw/workspace/answer-context";
import { CiteAnchor } from "@/components/singlaw/workspace/cite-link";

afterEach(cleanup);

const act: Source = {
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
  hierarchy_path: [],
  snippet: "",
  collection: "sg_law",
};
const repealed: Source = {
  ...act,
  n: 2,
  chunk_id: "c2",
  citation: "Old Act 1990, s 3",
  status: "repealed",
};
const judgment: Source = {
  ...act,
  n: 3,
  chunk_id: "c3",
  citation: "[2022] SGCA 60 at [3]",
  url: "https://www.judiciary.gov.sg/x",
  doc_type: "judgment",
  authority_tier: 4,
  treatment: "overruled",
  court: "Court of Appeal",
  decision_date: "2022-08-01",
};

describe("Citation helpers", () => {
  it("resolves only #cite-n hrefs", () => {
    expect(citeNumberFromHref("#cite-3")).toBe(3);
    expect(citeNumberFromHref("#cite-")).toBeNull();
    expect(citeNumberFromHref("https://sso.agc.gov.sg")).toBeNull();
    expect(citeNumberFromHref(undefined)).toBeNull();
  });

  it("holds back a partial marker while streaming and links complete ones", () => {
    expect(renderableAnswer("Notice is due [CITE:1] under [CI", true)).toBe(
      "Notice is due [1](#cite-1) under ",
    );
    expect(renderableAnswer("Notice is due [CITE:1] under [CI", false)).toBe(
      "Notice is due [1](#cite-1) under [CI",
    );
  });

  it("writes citations out in full for the clipboard and drops unresolved ones", () => {
    expect(textForClipboard("Notice is due. [CITE:1] Also [CITE:9].", [act])).toBe(
      "Notice is due. (Employment Act 1968, s 14) Also.",
    );
  });

  it("flags repealed and overruled authority with the worst severity", () => {
    expect(answerWarning([act])).toBeNull();
    expect(answerWarning([act, { ...act, n: 5, status: "not_yet_commenced" }])?.severity).toBe(
      "amber",
    );
    const warning = answerWarning([act, repealed, judgment]);
    expect(warning?.severity).toBe("red");
    expect(warning?.problems).toEqual([
      "Old Act 1990, s 3 (repealed)",
      "[2022] SGCA 60 at [3] (overruled)",
    ]);
  });

  it("explains low confidence from the backend's reason codes", () => {
    expect(lowConfidenceExplanation(["no_results"])).toContain(
      "nothing in the corpus answers this",
    );
    expect(lowConfidenceExplanation(["weak_relevance", "guidance_outranks_legislation"])).toContain(
      "only weakly relevant sources were found; guidance outranks legislation",
    );
    expect(lowConfidenceExplanation(undefined)).toMatch(/^Low confidence — /);
  });

  it("summarises filtered provisions", () => {
    expect(filteredSummary({ repealed: 2, spent: 0, not_yet_commenced: 1 })).toBe(
      "2 repealed provisions excluded as no longer in force; 1 provision not yet in force excluded",
    );
    expect(filteredSummary({ repealed: 0, spent: 0, not_yet_commenced: 0 })).toBeNull();
  });
});

describe("Citation chips", () => {
  const renderWith = (sources: Source[], href: string, openSource = vi.fn()) => {
    render(
      <AnswerContext.Provider value={{ sources, invalidCites: [], openSource }}>
        <CiteAnchor href={href}>{href.replace("#cite-", "")}</CiteAnchor>
      </AnswerContext.Provider>,
    );
    return openSource;
  };

  it("shows the legal citation, never a bare number, and opens the source on click", () => {
    const openSource = renderWith([act], "#cite-1");
    const chip = screen.getByRole("button", { name: "Open source: Employment Act 1968, s 14" });
    expect(chip).toHaveTextContent("Employment Act 1968, s 14");
    expect(chip).not.toHaveTextContent(/^1$/);
    fireEvent.click(chip);
    expect(openSource).toHaveBeenCalledWith(act);
  });

  it("marks repealed or overruled sources", () => {
    renderWith([judgment], "#cite-3");
    expect(screen.getByRole("button", { name: /SGCA 60/ })).toHaveAttribute("data-severity", "red");
  });

  it("renders an unresolvable number as a muted marker", () => {
    renderWith([act], "#cite-7");
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByTitle("source not found")).toHaveTextContent("[7]");
  });

  it("leaves ordinary links as external links", () => {
    renderWith([act], "https://sso.agc.gov.sg/Act/EmA1968");
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "https://sso.agc.gov.sg/Act/EmA1968");
    expect(link).toHaveAttribute("target", "_blank");
  });
});
