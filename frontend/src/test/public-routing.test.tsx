import { QueryClient } from "@tanstack/react-query";
import { createRouter, rootRouteId } from "@tanstack/react-router";
import { describe, expect, it } from "vitest";

import { routeTree } from "@/routeTree.gen";
import {
  validateDocSearch,
  validateSourcesSearch,
} from "@/components/singlaw/explorer/search-params";

// Match routes without running loaders or rendering (see app-routing.test.tsx).
describe("Public routes", () => {
  const router = createRouter({ routeTree, context: { queryClient: new QueryClient() } });

  it("matches /sources/some-doc to the document explorer", () => {
    const last = router.matchRoutes("/sources/some-doc").at(-1);
    expect(last?.routeId).toBe("/sources_/$docId");
    expect(last?.params).toEqual({ docId: "some-doc" });
  });

  it("keeps /sources on the corpus explorer and off the not-found page", () => {
    const last = router.matchRoutes("/sources").at(-1);
    expect(last?.routeId).toBe("/sources");
    expect(last?.routeId).not.toBe(rootRouteId);
  });

  it.each(["/welcome", "/billing", "/terms"])("still serves %s", (path) => {
    expect(router.matchRoutes(path).at(-1)?.routeId).toBe(path);
  });

  it("accepts only a non-empty string chunk param on the document page", () => {
    expect(validateDocSearch({ chunk: "employment-act-1968:s14" })).toEqual({
      chunk: "employment-act-1968:s14",
    });
    expect(validateDocSearch({ chunk: 3 })).toEqual({});
    expect(validateDocSearch({ chunk: "" })).toEqual({});
    expect(validateDocSearch({})).toEqual({});
  });

  it("normalises the explorer's mode, query and type params", () => {
    expect(validateSourcesSearch({ mode: "search", q: "  notice period ", type: "act" })).toEqual({
      mode: "search",
      q: "notice period",
      type: "act",
    });
    expect(validateSourcesSearch({ mode: "browse", q: "   ", type: "all" })).toEqual({});
    expect(validateSourcesSearch({ type: "bogus" })).toEqual({});
  });
});
