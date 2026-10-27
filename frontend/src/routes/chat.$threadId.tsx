import { createFileRoute } from "@tanstack/react-router";
import { ChatPage } from "@/components/singlaw/chat";
import { metadata } from "@/lib/singlaw";
export const Route = createFileRoute("/chat/$threadId")({
  head: () =>
    metadata(
      "Your legal conversation",
      "Continue your SingLaw conversation about Singapore law, with every answer cited to its source.",
    ),
  component: ThreadPage,
});
function ThreadPage() {
  const { threadId } = Route.useParams();
  return <ChatPage key={threadId} threadId={threadId} />;
}
