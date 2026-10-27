import { createFileRoute } from "@tanstack/react-router";
import { ChatPage } from "@/components/singlaw/chat";
import { metadata } from "@/lib/singlaw";
export const Route = createFileRoute("/")({
  // `/?q=…` pre-fills the composer (used by "Ask about this provision" in the explorer)
  validateSearch: (search: Record<string, unknown>): { q?: string } =>
    typeof search["q"] === "string" && search["q"].trim() ? { q: search["q"] } : {},
  head: () =>
    metadata(
      "Your Singapore legal companion",
      "Ask SingLaw about Singapore law and get answers grounded in the provisions and judgments they cite.",
    ),
  component: Index,
});
function Index() {
  const { q } = Route.useSearch();
  return <ChatPage initialQuestion={q} />;
}
