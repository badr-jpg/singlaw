import { useSyncExternalStore } from "react";
import { SELECTED_BUSINESS_KEY } from "@/lib/singlaw";

export type QuestionMode = "personal" | "business";

interface ScopeState {
  mode: QuestionMode;
  businessId: string | null;
}

const CHANGE_EVENT = "singlaw:scope";
const SERVER_STATE: ScopeState = { mode: "personal", businessId: null };

let state: ScopeState | null = null;

function readStoredBusiness(): string | null {
  try {
    return localStorage.getItem(SELECTED_BUSINESS_KEY);
  } catch {
    return null;
  }
}

function current(): ScopeState {
  if (!state) state = { mode: "personal", businessId: readStoredBusiness() };
  return state;
}

function commit(next: ScopeState) {
  state = next;
  try {
    if (next.businessId) localStorage.setItem(SELECTED_BUSINESS_KEY, next.businessId);
    else localStorage.removeItem(SELECTED_BUSINESS_KEY);
  } catch {
    // Storage unavailable: the selection still lives for this session.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function subscribe(listener: () => void) {
  window.addEventListener(CHANGE_EVENT, listener);
  return () => window.removeEventListener(CHANGE_EVENT, listener);
}

export function setQuestionMode(mode: QuestionMode) {
  commit({ ...current(), mode });
}

/** Selecting a business is an expression of intent, so it also switches to business mode. */
export function selectBusiness(businessId: string | null) {
  commit({ mode: businessId ? "business" : current().mode, businessId });
}

/**
 * Session-level question scope. Only the selected business id persists in
 * localStorage; the personal/business mode resets per browser session.
 */
export function useWorkspaceScope() {
  const scope = useSyncExternalStore(subscribe, current, () => SERVER_STATE);
  return { ...scope, setMode: setQuestionMode, selectBusiness };
}
