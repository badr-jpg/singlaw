import { Link } from 'react-router-dom'
import { Wordmark } from '../components/Wordmark'
import { useApp } from '../context/AppContext'
import { usePageTitle } from '../hooks/usePageTitle'

const NAV_LINKS = [
  { href: '#features', label: 'Features' },
  { href: '#how-it-works', label: 'How it works' },
  { href: '#trust', label: 'Trust' },
]

/**
 * Marketing landing page for Singapore private citizens and small businesses.
 * Everything on this page describes real behaviour of the product — no
 * invented numbers, testimonials or logos.
 */
export function LandingPage() {
  usePageTitle('SG Law Assistant — Singapore law, plainly answered, fully cited')
  const { attribution } = useApp()

  return (
    <div className="min-h-0 flex-1 scroll-smooth overflow-y-auto bg-paper-25">
      {/* ------------------------------------------------------------ nav */}
      <header className="sticky top-0 z-30 border-b border-paper-200 bg-paper-25/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-5 py-3">
          <Link to="/" className="flex items-center gap-2.5" aria-label="SG Law Assistant home">
            <Wordmark className="h-8 w-8" />
            <span className="text-[15px] font-semibold tracking-tight text-ink-950">
              SG Law Assistant
            </span>
          </Link>
          <nav className="ml-auto hidden items-center gap-6 sm:flex" aria-label="Landing sections">
            {NAV_LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="text-sm font-medium text-paper-700 transition-colors hover:text-ink-900"
              >
                {l.label}
              </a>
            ))}
          </nav>
          <Link to="/chat" className="btn-primary ml-auto sm:ml-0">
            Open the assistant
          </Link>
        </div>
      </header>

      <main>
        {/* ----------------------------------------------------------- hero */}
        <section className="border-b border-paper-200 bg-paper-25">
          <div className="mx-auto grid max-w-6xl gap-12 px-5 py-16 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:py-20">
            <div>
              <p className="text-[13px] font-semibold tracking-[0.14em] text-accent-600 uppercase">
                Legal information for Singapore
              </p>
              <h1 className="mt-3 font-serif text-4xl leading-[1.12] font-bold tracking-tight text-ink-950 sm:text-5xl">
                Understand the Singapore law that applies to you.
              </h1>
              <p className="mt-5 max-w-xl text-lg leading-8 text-paper-700">
                Ask in plain English. Every sentence of every answer is backed by a citation to the
                actual statute or judgment it relies on — and you can open each cited provision and
                read it yourself.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link to="/chat" className="btn-primary px-6 py-2.5 text-base">
                  Ask a question
                </Link>
                <Link to="/explorer" className="btn-secondary px-6 py-2.5 text-base">
                  Browse the law
                </Link>
              </div>
              <p className="mt-5 text-[13px] leading-5 text-paper-600">
                Legal information, not legal advice — every answer says so, and high-stakes
                questions are pointed to real professional help.
              </p>
            </div>

            <HeroMock />
          </div>
        </section>

        {/* ------------------------------------------------------- features */}
        <section id="features" className="scroll-mt-16 bg-paper-50">
          <div className="mx-auto max-w-6xl px-5 py-16">
            <h2 className="font-serif text-3xl font-bold tracking-tight text-ink-950">
              Built for people who need the answer to be true
            </h2>
            <p className="mt-3 max-w-2xl text-base leading-7 text-paper-700">
              Not a chatbot with opinions about the law — a retrieval system over the law itself,
              with every safeguard visible.
            </p>
            <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              <BenefitCard
                icon={<IconCite />}
                title="Every claim, cited"
                body="Each sentence of an answer carries a citation chip linking to the provision or judgment it relies on. Click any chip to read the source in full, with a link to the official text."
              />
              <BenefitCard
                icon={<IconShield />}
                title="Current law only"
                body="Repealed provisions and overruled judgments are flagged in red and never silently served as good law. Every answer states the date of the law it is based on."
              />
              <BenefitCard
                icon={<IconChat />}
                title="Plain English in, actual statute out"
                body="Describe your situation the way you would tell a friend. The answer quotes the legislation and case law that actually applies — not a paraphrase of a paraphrase."
              />
              <BenefitCard
                icon={<IconLock />}
                title="Your documents stay on your machine"
                body="Upload a contract or letter and ask about your own situation. All retrieval and indexing runs locally — only the final answer generation calls an external model."
              />
              <BenefitCard
                icon={<IconBrowse />}
                title="Browse the corpus yourself"
                body="A full explorer walks each Act from Part to Division to Section, with version history and the judgments that cite every provision. You never have to take the assistant's word for it."
              />
              <BenefitCard
                icon={<IconInspect />}
                title="See exactly why an answer was given"
                body="A retrieval inspector under each answer shows what was searched, what was filtered out and why, and how the cited sources were ranked."
              />
            </div>
          </div>
        </section>

        {/* --------------------------------------------------- how it works */}
        <section id="how-it-works" className="scroll-mt-16 border-y border-paper-200 bg-paper-25">
          <div className="mx-auto max-w-6xl px-5 py-16">
            <h2 className="font-serif text-3xl font-bold tracking-tight text-ink-950">
              How it works
            </h2>
            <div className="mt-10 grid gap-8 md:grid-cols-3">
              <Step
                n={1}
                title="Ask in plain English"
                body="Type your question the way you would ask a person — no statute names or legal jargon needed."
              />
              <Step
                n={2}
                title="We retrieve the law itself"
                body="The system searches the actual provisions and judgments, filters out anything repealed or not yet in force, and ranks what remains by relevance and authority."
              />
              <Step
                n={3}
                title="You get a cited, dated answer"
                body="Every proposition carries a citation, the answer states the date of the law it relies on, and each source links to the official text."
              />
            </div>
          </div>
        </section>

        {/* ---------------------------------------------------------- trust */}
        <section id="trust" className="scroll-mt-16 bg-ink-950">
          <div className="mx-auto max-w-6xl px-5 py-16">
            <h2 className="font-serif text-3xl font-bold tracking-tight text-paper-25">
              Built to be checked, not believed
            </h2>
            <div className="mt-10 grid gap-x-10 gap-y-8 md:grid-cols-2">
              <TrustItem title="Legal information, not legal advice">
                The assistant explains what the law says; it does not tell you what to do. No
                lawyer–client relationship is created, it refuses to draft filings or court
                documents, and a non-dismissible disclaimer stays on screen at all times.
              </TrustItem>
              <TrustItem title="Official sources, properly attributed">
                {attribution}
              </TrustItem>
              <TrustItem title="High-stakes questions get real referrals">
                When a question looks high-stakes, the assistant says so openly and points you to
                pro bono and legal-aid services — because some situations need a professional, not
                a chat window.
              </TrustItem>
              <TrustItem title="A transparent, dated corpus">
                The corpus is synced from official sources on a fixed schedule, every document
                records its source URL and version date, and the app shows when the corpus was
                last synced — so you always know how fresh the law you are reading is.
              </TrustItem>
            </div>
          </div>
        </section>
      </main>

      {/* --------------------------------------------------------- footer */}
      <footer className="border-t border-paper-200 bg-paper-50">
        <div className="mx-auto max-w-6xl px-5 py-10">
          <div className="flex flex-wrap items-start justify-between gap-8">
            <div className="max-w-md">
              <div className="flex items-center gap-2.5">
                <Wordmark className="h-7 w-7" />
                <span className="text-sm font-semibold text-ink-950">SG Law Assistant</span>
              </div>
              <p className="mt-3 text-[13px] leading-5 text-paper-600">
                This assistant provides legal information, not legal advice. Using it creates no
                lawyer–client relationship. For advice on your specific situation, consult a
                qualified Singapore lawyer.
              </p>
            </div>
            <nav aria-label="Footer" className="flex gap-12 text-sm">
              <div>
                <p className="mb-2 text-[11px] font-semibold tracking-wide text-paper-500 uppercase">
                  Product
                </p>
                <ul className="space-y-1.5">
                  <li>
                    <Link to="/chat" className="text-paper-700 hover:text-ink-900">
                      Chat
                    </Link>
                  </li>
                  <li>
                    <Link to="/explorer" className="text-paper-700 hover:text-ink-900">
                      Source explorer
                    </Link>
                  </li>
                  <li>
                    <Link to="/documents" className="text-paper-700 hover:text-ink-900">
                      Your documents
                    </Link>
                  </li>
                </ul>
              </div>
              <div>
                <p className="mb-2 text-[11px] font-semibold tracking-wide text-paper-500 uppercase">
                  Official sources
                </p>
                <ul className="space-y-1.5">
                  <li>
                    <a
                      href="https://sso.agc.gov.sg"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-paper-700 hover:text-ink-900"
                    >
                      Singapore Statutes Online
                    </a>
                  </li>
                  <li>
                    <a
                      href="https://www.judiciary.gov.sg"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-paper-700 hover:text-ink-900"
                    >
                      Singapore Courts
                    </a>
                  </li>
                </ul>
              </div>
            </nav>
          </div>
          <p className="mt-8 border-t border-paper-200 pt-4 text-[11px] leading-4 text-paper-500">
            {attribution}
          </p>
        </div>
      </footer>
    </div>
  )
}

/* ------------------------------------------------------------------------- */
/* Hero product mock — a static, styled DOM rendition of a real chat answer. */
/* ------------------------------------------------------------------------- */

function MockChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="mx-0.5 inline rounded-sm border border-ink-200 bg-ink-50 px-1 py-px align-baseline font-sans text-[11px] leading-4 font-medium text-ink-800">
      {children}
    </span>
  )
}

function HeroMock() {
  return (
    <div
      className="rounded-xl border border-paper-200 bg-white shadow-panel"
      role="img"
      aria-label="Illustration of an assistant answer with inline legal citations"
    >
      <div className="flex items-center gap-2 border-b border-paper-200 px-4 py-2.5">
        <Wordmark className="h-5 w-5" />
        <span className="text-xs font-semibold text-ink-900">SG Law Assistant</span>
        <span className="meta-chip ml-auto border-paper-300 bg-paper-50 text-paper-600">
          Illustration
        </span>
      </div>
      <div className="space-y-4 px-4 py-4">
        <div className="flex justify-end">
          <div className="max-w-[85%] rounded-lg rounded-br-sm bg-ink-900 px-3.5 py-2 text-[13px] leading-5 text-white">
            How much notice must my employer give to end my employment?
          </div>
        </div>
        <div className="font-serif text-[13.5px] leading-6 text-ink-950">
          If your contract is silent, the Employment Act sets the minimum notice by length of
          service — an employee of five years or more is entitled to 4 weeks&rsquo; notice{' '}
          <MockChip>Employment Act 1968, s&nbsp;10(3)</MockChip>. Either party may also waive
          notice, or pay salary in lieu of it{' '}
          <MockChip>Employment Act 1968, s&nbsp;11</MockChip>.
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="meta-chip border-ink-200 bg-ink-50 text-ink-800">Tier 2 · Act</span>
          <span className="meta-chip border-positive-300 bg-positive-50 text-positive-800">
            In force
          </span>
          <span className="meta-chip border-paper-300 bg-paper-50 text-paper-700">
            Current version
          </span>
        </div>
        <p className="border-t border-paper-200 pt-2.5 text-[10.5px] leading-4 text-paper-500">
          Click any citation to read the provision in full, with a link to the official source.
        </p>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------------- */
/* Small presentational pieces                                               */
/* ------------------------------------------------------------------------- */

function BenefitCard({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode
  title: string
  body: string
}) {
  return (
    <div className="rounded-lg border border-paper-200 bg-white p-5 shadow-card">
      <div className="flex h-9 w-9 items-center justify-center rounded-md bg-ink-50 text-ink-700">
        {icon}
      </div>
      <h3 className="mt-3.5 text-[15px] font-semibold text-ink-950">{title}</h3>
      <p className="mt-1.5 text-[13.5px] leading-6 text-paper-700">{body}</p>
    </div>
  )
}

function Step({ n, title, body }: { n: number; title: string; body: string }) {
  return (
    <div>
      <div className="flex items-center gap-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-100 font-serif text-[15px] font-bold text-accent-700">
          {n}
        </span>
        <h3 className="text-base font-semibold text-ink-950">{title}</h3>
      </div>
      <p className="mt-2.5 text-sm leading-6 text-paper-700 md:pl-11">{body}</p>
    </div>
  )
}

function TrustItem({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-[15px] font-semibold text-paper-25">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-ink-200">{children}</p>
    </div>
  )
}

/* Icons — 16px stroke glyphs, inherit currentColor. */

function IconCite() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 fill-current" aria-hidden="true">
      <path d="M4 1.5h6.5L13 4v10.5H4V1.5Zm1.5 4h5v1.2h-5V5.5Zm0 2.6h5v1.2h-5V8.1Zm0 2.6h3.5v1.2H5.5v-1.2Z" />
    </svg>
  )
}

function IconShield() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 fill-current" aria-hidden="true">
      <path d="M8 1 2.5 3v4.2c0 3.4 2.3 6.1 5.5 7.3 3.2-1.2 5.5-3.9 5.5-7.3V3L8 1Zm-.9 9.4L4.7 8l1-1 1.4 1.4L10.3 5l1 1-4.2 4.4Z" />
    </svg>
  )
}

function IconChat() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 fill-current" aria-hidden="true">
      <path d="M2 3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H8l-4 3v-3H3a1 1 0 0 1-1-1V3Z" />
    </svg>
  )
}

function IconLock() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 fill-current" aria-hidden="true">
      <path d="M8 1.5A3.5 3.5 0 0 0 4.5 5v2H4a1 1 0 0 0-1 1v5a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1h-.5V5A3.5 3.5 0 0 0 8 1.5ZM6 5a2 2 0 1 1 4 0v2H6V5Z" />
    </svg>
  )
}

function IconBrowse() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 fill-current" aria-hidden="true">
      <path d="M2 2h5a2 2 0 0 1 1 .3A2 2 0 0 1 9 2h5v11h-5a1 1 0 0 0-1 1 1 1 0 0 0-1-1H2V2Zm1.5 1.5v8H7a2 2 0 0 1 .3.02V4a1 1 0 0 0-1-.5H3.5Zm9 0H9.7a1 1 0 0 0-1 .5v7.52a2 2 0 0 1 .3-.02h3.5v-8Z" />
    </svg>
  )
}

function IconInspect() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 fill-current" aria-hidden="true">
      <path d="M6.5 1a5.5 5.5 0 1 0 3.4 9.8l3.1 3.2 1.1-1.1-3.2-3.1A5.5 5.5 0 0 0 6.5 1Zm0 1.8a3.7 3.7 0 1 1 0 7.4 3.7 3.7 0 0 1 0-7.4Z" />
    </svg>
  )
}
