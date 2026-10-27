import { createFileRoute, Link } from "@tanstack/react-router";
import { PublicLayout } from "@/components/singlaw/shell";
import { metadata } from "@/lib/singlaw";
import {
  AGC_ATTRIBUTION,
  HIGH_STAKES_REFERRALS,
  SSO_URL,
} from "@/components/singlaw/explorer/attribution";
import "@/public.css";

export const Route = createFileRoute("/terms")({
  head: () =>
    metadata(
      "Terms & privacy",
      "How SingLaw's answers are produced and checked, what it is not, which sources it uses, and what happens to your conversations, documents and billing.",
    ),
  component: Terms,
});

function Terms() {
  return (
    <PublicLayout>
      <main className="public-page legal-copy enter">
        <span className="eyebrow">Terms & privacy</span>
        <h1>A little transparency.</h1>
        <p>
          SingLaw is a retrieval-augmented legal-information assistant for Singapore law. This page
          says plainly how it works, what it is not, and what happens to what you give it.
        </p>

        <h2>About these answers</h2>
        <p>
          Answers are generated from provisions and judgments retrieved from SingLaw's indexed
          corpus — not from a model's memory. Retrieval, ranking, document analysis and storage run
          on the SingLaw server. The final wording of an answer is produced by a third-party
          language-model API, which receives your question, the retrieved excerpts and, when you
          attach a document, relevant excerpts of that document.
        </p>
        <ul>
          <li>Every sentence of an answer carries a citation to a retrieved source.</li>
          <li>Every answer states the date it is current to (its “as at” date).</li>
          <li>Repealed legislation and overruled judgments are flagged, never silently served.</li>
          <li>
            A grounding check flags any sentence that could not be matched to a source, and SingLaw
            says when its confidence is low.
          </li>
        </ul>
        <p>
          Limits: the corpus is not the whole of Singapore law, retrieval can miss the right
          provision, and a cited passage can still be misread. Treat an answer as a well-referenced
          starting point and open the sources it cites.
        </p>

        <h2>Not legal advice</h2>
        <p>
          SingLaw provides legal information, not legal advice. It explains what the law says; it
          cannot tell you what to do in your specific situation, and using it creates no
          lawyer–client relationship. It does not draft documents for court and will decline to. For
          advice on your own matter, consult a lawyer.
        </p>
        <p>
          On high-stakes questions — criminal matters, immigration, deadlines and limitation
          periods, eviction — SingLaw surfaces referrals to:
        </p>
        <ul>
          {HIGH_STAKES_REFERRALS.map((r) => (
            <li key={r.name}>
              <a href={r.url} target="_blank" rel="noreferrer">
                {r.name}
              </a>
            </li>
          ))}
        </ul>

        <h2>Sources & attribution</h2>
        <p>
          The indexed corpus currently comprises legislation from Singapore Statutes Online (Acts
          and subsidiary legislation, including repealed Acts, which are flagged), Supreme Court
          judgments and Practice Directions. Agency guidance from MOM, HDB, Singapore Customs and
          the PDPC is on the roadmap and is not indexed; SingLaw will not cite it as a source.
        </p>
        <p>Wherever legislation text is displayed, the following notice applies:</p>
        <blockquote>{AGC_ATTRIBUTION}</blockquote>
        <p>
          Downloads from{" "}
          <a href={SSO_URL} target="_blank" rel="noreferrer">
            Singapore Statutes Online
          </a>{" "}
          are not authoritative texts — section 48 of the Interpretation Act 1965 does not apply to
          them; the Gazette is the authoritative text. Judgments and Practice Directions are
          reproduced from their official sources, and each is linked from the{" "}
          <Link to="/sources">corpus explorer</Link>.
        </p>

        <h2>Your conversations</h2>
        <p>
          Conversations are stored on the SingLaw server so you can return to them. You can rename
          or delete any conversation at any time from the workspace, and deleting it removes it from
          the server. Your questions are sent to the language-model provider as part of producing an
          answer, so avoid sharing more personal data than your question needs.
        </p>

        <h2>Your documents</h2>
        <p>
          Documents you attach are analysed on the SingLaw server so that the relevant parts can be
          read alongside the law when answering your question. Relevant excerpts of a document may
          be sent to the language-model provider as part of answering. Documents are stored until
          you delete them from the workspace; deleting a business workspace deletes its documents
          too. Your documents are context for your question, never treated as legal authority.
        </p>

        <h2>Billing</h2>
        <p>
          SingLaw offers a free Personal plan, a paid Business plan and a Teams plan on request.
          Current prices, in Singapore dollars, and each plan's limits are shown on the{" "}
          <Link to="/billing">plans page</Link>. When checkout is active, payments and subscriptions
          are processed by Stripe; SingLaw does not see or store your card details. Until checkout
          is active no payment is taken, and you can join a plan's waitlist instead.
        </p>

        <p className="xp-updated">Last updated: 7 October 2026</p>
      </main>
    </PublicLayout>
  );
}
