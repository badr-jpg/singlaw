import { Wordmark } from './Wordmark'

const EXAMPLE_QUESTIONS = [
  'What notice period must my employer give before terminating my employment?',
  'Can my landlord keep my security deposit if I end the tenancy early?',
  'What are the requirements for a valid will in Singapore?',
  'How do I make a claim in the Small Claims Tribunals, and what is the limit?',
]

/**
 * Designed empty state for a new conversation: explains what the assistant is
 * and is not, and offers example questions as one-click starters.
 */
export function EmptyState({ onAsk }: { onAsk: (question: string) => void }) {
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col justify-center px-6 py-10">
      <div className="mb-2 flex items-center gap-3">
        <Wordmark className="h-10 w-10" />
        <h2 className="font-serif text-2xl font-bold tracking-tight text-ink-950">
          SG Law Assistant
        </h2>
      </div>

      <p className="text-sm leading-6 text-paper-700">
        Ask a question about Singapore law and get an answer grounded in the actual text of
        legislation and judgments — every proposition is cited, and you can open each cited
        provision to read it yourself.
      </p>

      <div className="mt-5 grid gap-3 text-xs leading-5 sm:grid-cols-2">
        <div className="rounded-md border border-positive-200 bg-positive-50/60 p-3">
          <h3 className="mb-1 font-semibold text-positive-900">What this is</h3>
          <ul className="list-disc space-y-0.5 pl-4 text-positive-900/90">
            <li>Legal information from Singapore statutes and case law</li>
            <li>Every answer cites its sources and states its temporal basis</li>
            <li>Repealed and overruled material is flagged, never hidden</li>
          </ul>
        </div>
        <div className="rounded-md border border-caution-200 bg-caution-50/60 p-3">
          <h3 className="mb-1 font-semibold text-caution-900">What this is not</h3>
          <ul className="list-disc space-y-0.5 pl-4 text-caution-900/90">
            <li>Not legal advice, and no lawyer–client relationship</li>
            <li>It will not draft filings or court documents</li>
            <li>For high-stakes matters, it points you to real help</li>
          </ul>
        </div>
      </div>

      <h3 className="mt-6 mb-2 text-[11px] font-semibold tracking-wide text-paper-600 uppercase">
        Try asking
      </h3>
      <div className="flex flex-col gap-2">
        {EXAMPLE_QUESTIONS.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onAsk(q)}
            className="rounded-md border border-paper-200 bg-white px-3.5 py-2.5 text-left text-sm text-ink-800 shadow-card transition-colors hover:border-ink-300 hover:bg-ink-50 hover:text-ink-950"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}
