import { useState, type FormEvent, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  CalendarCheck,
  Check,
  CheckCircle2,
  CreditCard,
  Eye,
  Files,
  LibraryBig,
  MessageCircle,
  RefreshCw,
  SearchCheck,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { api, ApiError, type Plan } from "@/lib/api";
import { Modal } from "./shell";
import { SourceLogo } from "./source-logo";
import { ExplorerBadge } from "./explorer/badges";
import { formatCount } from "./explorer/helpers";
import {
  formatLimit,
  limitBadges,
  planAction,
  planPrice,
  usageRatio,
  usageRows,
  type BillingInterval,
  type UsageRow,
} from "./explorer/pricing";
import { errorMessage } from "./explorer/errors";
import { LinesSkeleton } from "./explorer/states";

export function Reveal({ children, className = "" }: { children: ReactNode; className?: string }) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduced ? false : { opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.1 }}
      transition={{ duration: 0.65 }}
    >
      {children}
    </motion.div>
  );
}

function Cite({ n }: { n: number }) {
  return (
    <span className="marketing-cite" aria-label={`Citation ${n}`}>
      {n}
    </span>
  );
}

/** A static example of a SingLaw answer. It is labelled as such; it is not a live call. */
export function ProductPreview() {
  return (
    <Reveal className="marketing-product">
      <div className="marketing-product-bar">
        <span className="marketing-window-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span>A cited answer, in plain English</span>
        <BookOpen size={16} />
      </div>
      <div className="marketing-product-body">
        <div className="marketing-preview-head">
          <span className="eyebrow">What an answer looks like</span>
          <span className="marketing-example-tag">
            <Eye aria-hidden="true" /> Example · not a live answer
          </span>
        </div>
        <div className="marketing-chat-row">
          <span className="marketing-avatar user">U</span>
          <p>Can my employer fire me on the spot for misconduct?</p>
        </div>
        <div className="marketing-chat-row">
          <span className="marketing-avatar">§</span>
          <div className="marketing-answer">
            <p>
              <strong>Only after a due inquiry.</strong> Under the Employment Act, an employer may
              dismiss an employee without notice on the ground of misconduct inconsistent with the
              conditions of service, but only after due inquiry.
              <Cite n={1} />
            </p>
            <p>
              If you believe the dismissal was without just cause or excuse, you can lodge a
              wrongful-dismissal claim within one month of the dismissal.
              <Cite n={1} /> Whether an inquiry was “due” is judged on the facts of each case.
              <Cite n={2} />
            </p>
            <p className="marketing-asat">
              <span>
                <b>As at</b> 7 Oct 2026
              </span>
              <span className="ok">
                <CheckCircle2 aria-hidden="true" /> 3 of 3 sentences grounded
              </span>
              <span>
                <b>Primary source</b> Act · in force
              </span>
            </p>
            <div className="marketing-citations">
              <Button asChild variant="outline">
                <Link to="/sources" search={{ mode: "search", q: "Employment Act 1968, s 14" }}>
                  <SourceLogo id="sso" /> [1] Employment Act 1968, s 14 <ArrowUpRight size={12} />
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link to="/sources" search={{ mode: "search", q: "[2022] SGCA 60" }}>
                  <SourceLogo id="courts" /> [2] [2022] SGCA 60 <ArrowUpRight size={12} />
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
      <div className="marketing-preview-footer">
        <span>
          Legal information, not legal advice. Every sentence cites the source it came from.
        </span>
        <Link to="/">
          Ask your own question <ArrowRight size={13} />
        </Link>
      </div>
    </Reveal>
  );
}

const publishers = [
  { id: "sso", label: "Singapore Statutes Online" },
  { id: "courts", label: "Supreme Court judgments" },
  { id: "courts", label: "Practice Directions" },
];
export function SourceMarquee() {
  return (
    <section className="marketing-sources" aria-label="Indexed sources">
      <p className="marketing-kicker">What SingLaw answers from</p>
      <div className="marketing-marquee">
        <div className="marketing-marquee-track">
          {[0, 1].map((copy) => (
            <div className="marketing-marquee-group" key={copy} aria-hidden={copy === 1}>
              {publishers.map((p) => (
                <Link to="/sources" key={p.label} tabIndex={copy === 1 ? -1 : 0}>
                  <SourceLogo id={p.id} />
                  <span>{p.label}</span>
                </Link>
              ))}
            </div>
          ))}
        </div>
      </div>
      <p className="marketing-fineprint">
        Acts and subsidiary legislation (repealed Acts flagged), Supreme Court judgments and
        Practice Directions. More sources on the roadmap: MOM, HDB, Customs, PDPC.
      </p>
    </section>
  );
}

export function Benefits() {
  return (
    <section className="marketing-benefits">
      <div className="marketing-inner">
        <Reveal className="marketing-benefits-heading">
          <p className="marketing-kicker">Built to be checked</p>
          <h2>
            Answers you can
            <br />
            <em>open and read.</em>
          </h2>
        </Reveal>
      </div>
      <div className="marketing-inner marketing-three">
        {[
          {
            icon: BookOpen,
            title: "Every sentence cited.",
            copy: "Answers are built only from provisions and judgments retrieved from the indexed corpus. Each sentence carries a citation you can open — and read in full in the explorer.",
          },
          {
            icon: CalendarCheck,
            title: "Current, and says so.",
            copy: "Every answer states the date it is current to. Repealed Acts and overruled judgments are flagged, never silently served as the law.",
          },
          {
            icon: MessageCircle,
            title: "Plain English in, statute out.",
            copy: "Ask the way you would ask a friend. SingLaw works out whether you need a provision, a procedure or a case, then finds the Act, the section and the judgments.",
          },
          {
            icon: Files,
            title: "Your documents, in context.",
            copy: "Attach a contract or a letter and the relevant excerpts are read alongside the law. Documents stay on SingLaw's server only until you delete them.",
          },
          {
            icon: LibraryBig,
            title: "Explore the corpus yourself.",
            copy: "Browse every indexed Act, regulation, judgment and Practice Direction, with its status, authority tier, version history and the judgments that cite it.",
          },
          {
            icon: SearchCheck,
            title: "See how an answer was found.",
            copy: "Open the retrieval behind any answer: which passages were considered, how they ranked, and any sentence the grounding check could not match to a source.",
          },
        ].map(({ icon: Icon, title, copy }) => (
          <Reveal key={title}>
            <Icon size={26} />
            <h3>{title}</h3>
            <p>{copy}</p>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- plans

type WaitlistReason = "unavailable" | "checkout";

export function MarketingPlans() {
  const [annual, setAnnual] = useState(false);
  const interval: BillingInterval = annual ? "yearly" : "monthly";
  const [waitlist, setWaitlist] = useState<{ plan: Plan; reason: WaitlistReason } | null>(null);

  const plans = useQuery({ queryKey: ["plans"], queryFn: api.plans, staleTime: 5 * 60_000 });
  const status = useQuery({
    queryKey: ["billing-status"],
    queryFn: api.billingStatus,
    staleTime: 60_000,
    retry: false,
  });
  const checkout = useMutation({
    mutationFn: ({ plan }: { plan: Plan }) => api.checkout(plan.id, interval),
    onSuccess: ({ url }) => {
      if (url) window.location.assign(url);
      else toast.error("Checkout didn't return a payment link. Please try again.");
    },
    onError: (error, { plan }) => {
      if (error instanceof ApiError && error.status === 503) {
        setWaitlist({ plan, reason: "checkout" });
      } else {
        toast.error(errorMessage(error));
      }
    },
  });

  const checkoutAvailable = status.data?.checkout_available;
  const fineprint =
    checkoutAvailable === undefined
      ? "Prices in SGD."
      : checkoutAvailable
        ? "Prices in SGD. Cancel anytime."
        : "Prices in SGD. Checkout opens soon — join the waitlist to be first.";

  return (
    <section className="marketing-plans marketing-inner" id="plans" aria-labelledby="plans-heading">
      <Reveal className="marketing-plans-heading">
        <h2 id="plans-heading">Start free. Upgrade when your questions do.</h2>
        <p>
          Personal for everyday life. Business for the company you run. Teams when more than one of
          you needs answers.
        </p>
        <div className="marketing-period">
          <span className={!annual ? "selected" : ""}>Monthly</span>
          <Switch checked={annual} onCheckedChange={setAnnual} aria-label="Yearly billing" />
          <span className={annual ? "selected" : ""}>Yearly</span>
        </div>
        <p className="marketing-fineprint">{fineprint}</p>
      </Reveal>

      {plans.isPending ? (
        <div className="marketing-three marketing-plan-grid xp-plans-loading" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div className="marketing-plan" key={i}>
              <LinesSkeleton lines={6} label="Loading plans" />
            </div>
          ))}
        </div>
      ) : plans.error ? (
        <div className="library-empty xp-error" role="alert">
          <strong>The plans didn't load</strong>
          <p>{errorMessage(plans.error)}</p>
          <Button variant="outline" size="sm" onClick={() => plans.refetch()}>
            <RefreshCw /> Try again
          </Button>
        </div>
      ) : (
        <div className="marketing-three marketing-plan-grid">
          {plans.data.plans.map((plan) => (
            <PlanCard
              key={plan.id}
              plan={plan}
              interval={interval}
              currentPlanId={status.data?.plan ?? null}
              busy={checkout.isPending && checkout.variables?.plan.id === plan.id}
              onCheckout={(p) => checkout.mutate({ plan: p })}
              onWaitlist={(p, reason) => setWaitlist({ plan: p, reason })}
            />
          ))}
        </div>
      )}

      {waitlist && (
        <WaitlistModal
          plan={waitlist.plan}
          reason={waitlist.reason}
          close={() => setWaitlist(null)}
        />
      )}
    </section>
  );
}

function PlanCard({
  plan,
  interval,
  currentPlanId,
  busy,
  onCheckout,
  onWaitlist,
}: {
  plan: Plan;
  interval: BillingInterval;
  currentPlanId: string | null;
  busy: boolean;
  onCheckout: (plan: Plan) => void;
  onWaitlist: (plan: Plan, reason: WaitlistReason) => void;
}) {
  const price = planPrice(plan, interval);
  const action = planAction(plan, currentPlanId);
  const primary = plan.featured ? "default" : "outline";
  return (
    <Reveal className={`marketing-plan ${plan.featured ? "featured" : ""}`}>
      <div className="marketing-plan-heading">
        <h3>{plan.name}</h3>
        {action === "current" ? (
          <span>Your plan</span>
        ) : plan.featured ? (
          <span>Featured</span>
        ) : null}
      </div>
      <div className="marketing-price" aria-live="polite">
        {price.label}
      </div>
      <p className="marketing-fineprint marketing-price-note">{price.note ?? ""}</p>
      <p className="marketing-plan-description">{plan.description}</p>
      <div className="marketing-plan-limits" aria-label="Plan limits">
        {limitBadges(plan.limits).map((b) => (
          <ExplorerBadge plain key={b}>
            {b}
          </ExplorerBadge>
        ))}
      </div>
      <ul>
        {plan.features.map((f) => (
          <li key={f}>
            <Check size={16} />
            <span>{f}</span>
          </li>
        ))}
      </ul>
      {action === "current" ? (
        <Button variant="outline" disabled>
          Current plan
        </Button>
      ) : action === "free" ? (
        <Button asChild variant={primary} className="w-full rounded-lg">
          <Link to="/">
            Start free <ArrowRight />
          </Link>
        </Button>
      ) : action === "checkout" ? (
        <Button variant={primary} disabled={busy} onClick={() => onCheckout(plan)}>
          {busy ? "Opening checkout…" : `Choose ${plan.name}`}
          <ArrowRight />
        </Button>
      ) : (
        <Button variant={primary} onClick={() => onWaitlist(plan, "unavailable")}>
          {plan.id === "teams" ? "Tell us about your team" : "Join the waitlist"}
          <ArrowRight />
        </Button>
      )}
    </Reveal>
  );
}

function WaitlistModal({
  plan,
  reason,
  close,
}: {
  plan: Plan;
  reason: WaitlistReason;
  close: () => void;
}) {
  const [email, setEmail] = useState("");
  const teams = plan.id === "teams";
  const join = useMutation({
    mutationFn: () => api.joinWaitlist(email.trim(), plan.id),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const title =
    reason === "checkout"
      ? `Be first when ${plan.name} checkout opens`
      : teams
        ? "Tell us about your team"
        : `Join the ${plan.name} waitlist`;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (email.trim()) join.mutate();
  };
  return (
    <Modal title={title} eyebrow="Waitlist" close={close}>
      {join.isSuccess ? (
        <>
          <div className="xp-waitlist-success" role="status">
            <CheckCircle2 size={16} aria-hidden="true" />
            <span>
              You're on the list for {plan.name}. We'll let you know at{" "}
              <strong>{email.trim()}</strong> when it opens.
            </span>
          </div>
          <div className="modal-actions">
            <Button onClick={close}>Done</Button>
            <Button asChild variant="outline">
              <Link to="/">Ask SingLaw meanwhile</Link>
            </Button>
          </div>
        </>
      ) : (
        <form className="xp-waitlist-form" onSubmit={submit}>
          <p>
            {reason === "checkout"
              ? `Checkout for ${plan.name} isn't open yet. Leave your email and you'll be the first to know when it is.`
              : teams
                ? "Teams is set up by hand for now. Leave your email and we'll be in touch about shared workspaces and team billing."
                : `${plan.name} isn't open yet. Leave your email and we'll let you know when it is.`}
          </p>
          <label htmlFor="waitlist-email">Email</label>
          <Input
            id="waitlist-email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
          <div className="modal-actions">
            <Button type="submit" disabled={join.isPending || !email.trim()}>
              {join.isPending ? "Joining…" : "Join the waitlist"} <ArrowRight />
            </Button>
            <Button type="button" variant="outline" onClick={close}>
              Not now
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------- billing status

export function BillingSummary() {
  const status = useQuery({
    queryKey: ["billing-status"],
    queryFn: api.billingStatus,
    staleTime: 60_000,
    retry: false,
  });
  const plans = useQuery({ queryKey: ["plans"], queryFn: api.plans, staleTime: 5 * 60_000 });
  const planName =
    plans.data?.plans.find((p) => p.id === status.data?.plan)?.name ?? status.data?.plan ?? "";
  return (
    <section className="marketing-billing-status marketing-inner" aria-labelledby="billing-heading">
      <div className="flex items-center gap-3">
        <CreditCard size={20} />
        <h2 id="billing-heading">Your billing</h2>
      </div>
      {status.isPending ? (
        <div className="mt-4">
          <LinesSkeleton lines={4} label="Loading billing status" />
        </div>
      ) : status.error ? (
        <>
          <p>Your billing status didn't load: {errorMessage(status.error)}</p>
          <Button variant="outline" size="sm" onClick={() => status.refetch()}>
            <RefreshCw /> Try again
          </Button>
        </>
      ) : (
        <>
          <div className="xp-billing-plan">
            <span>Current plan</span>
            <ExplorerBadge tone="brand" plain>
              {planName}
            </ExplorerBadge>
            {status.data.checkout_available ? (
              <ExplorerBadge tone="ok" plain>
                Checkout open
              </ExplorerBadge>
            ) : (
              <ExplorerBadge plain>Checkout not open yet</ExplorerBadge>
            )}
          </div>
          <div className="xp-billing-grid">
            {usageRows(status.data).map((row) => (
              <UsageMeter key={row.key} row={row} />
            ))}
          </div>
          <p className="xp-billing-note">
            To change plans, choose one above.{" "}
            {status.data.checkout_available
              ? "Paid plans are billed in SGD and payments are processed by Stripe."
              : "Paid checkout isn't open yet — join a plan's waitlist and we'll let you know when it is."}{" "}
            Usage counts everything in your workspace; delete conversations, documents or businesses
            there to free up room.
          </p>
          <Button asChild variant="link">
            <Link to="/">
              Back to your workspace <ArrowRight />
            </Link>
          </Button>
        </>
      )}
    </section>
  );
}

function UsageMeter({ row }: { row: UsageRow }) {
  const ratio = usageRatio(row.used, row.limit);
  const pct = ratio === null ? 0 : Math.round(ratio * 100);
  const tone = ratio === null ? "" : ratio >= 1 ? "full" : ratio >= 0.8 ? "warn" : "";
  return (
    <div className="xp-usage">
      <div className="xp-usage-head">
        <b>{row.label}</b>
        <span>
          {formatCount(row.used)}
          {row.limit === null ? " · unlimited" : ` of ${formatLimit(row.limit)}`}
        </span>
      </div>
      {ratio !== null && (
        <span
          className="xp-meter"
          role="meter"
          aria-label={`${row.label} used`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
        >
          <i className={tone} style={{ width: `${pct}%` }} />
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- the rest

export function MarketingClose() {
  return (
    <section className="marketing-close">
      <Reveal>
        <p className="marketing-kicker">Singapore law, cited and current.</p>
        <h2>
          Ask the question.
          <br />
          Read the source.
        </h2>
        <Button asChild size="lg">
          <Link to="/">
            Ask your first question <ArrowRight />
          </Link>
        </Button>
        <p className="marketing-fineprint">
          Legal information, not legal advice. Every answer cites the law it came from.
        </p>
      </Reveal>
    </section>
  );
}

export function HowItWorks() {
  return (
    <section className="marketing-how marketing-inner">
      <Reveal className="marketing-section-heading">
        <p className="marketing-kicker">How an answer is made</p>
        <h2>
          Retrieved first.
          <br />
          <em>Written second.</em>
        </h2>
        <p>Nothing is answered from memory. The law is found before a word is written.</p>
      </Reveal>
      <div className="marketing-three marketing-steps">
        {[
          {
            number: "01",
            title: "Ask in your own words.",
            copy: "Type the question as you'd ask a friend. SingLaw works out what kind of question it is — a provision, a procedure, your rights, or a case — and rewrites it for retrieval.",
          },
          {
            number: "02",
            title: "The law is retrieved and ranked.",
            copy: "Hybrid search over the indexed corpus finds candidate provisions and judgments. A re-ranker orders them by relevance and authority; repealed and overruled material is filtered out and flagged.",
          },
          {
            number: "03",
            title: "The answer is written — and checked.",
            copy: "A language model drafts the answer from those excerpts only, with a citation on every sentence and an as-at date. A grounding check flags any sentence it cannot match to a source.",
          },
        ].map((step) => (
          <Reveal key={step.number} className="marketing-step">
            <span className="marketing-step-number">{step.number}</span>
            <h3>{step.title}</h3>
            <p>{step.copy}</p>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

export function MarketingFAQ() {
  return (
    <section className="marketing-faq marketing-inner">
      <Reveal className="marketing-section-heading">
        <p className="marketing-kicker">Before your first question</p>
        <h2>
          A few things
          <br />
          <em>you might be wondering.</em>
        </h2>
      </Reveal>
      <Reveal>
        <Accordion type="single" collapsible className="marketing-faq-list">
          {[
            {
              question: "Is SingLaw a lawyer?",
              answer:
                "No. SingLaw gives legal information, not legal advice: it explains what the law says, with citations, but it cannot tell you what to do in your situation, and using it creates no lawyer–client relationship. It will not draft documents for court. On high-stakes questions — criminal, immigration, deadlines, eviction — it points you to Law Society Pro Bono Services, the Legal Aid Bureau and the Criminal Legal Aid Scheme (CLAS).",
            },
            {
              question: "Are answers checked against current Singapore law?",
              answer:
                "Yes. Answers are generated only from provisions and judgments retrieved from the indexed corpus, state the date they are current to, and flag repealed or overruled authority instead of serving it. A grounding check marks any sentence that could not be matched to a source. It is still information, not advice — and Singapore Statutes Online text is not the authoritative Gazette text.",
            },
            {
              question: "What happens to my conversations and documents?",
              answer:
                "Both are stored on the SingLaw server so you can come back to them, and you can delete either at any time from the workspace. Retrieval, ranking and document analysis run on the SingLaw server. The final wording of an answer comes from a third-party language-model API, which receives your question, the retrieved excerpts and — when you attach a document — the relevant excerpts of it. Share no more personal detail than your question needs.",
            },
            {
              question: "Do I need an account or a subscription?",
              answer:
                "The Personal plan is free to start. Business is a paid plan with larger document and business-workspace allowances, and Teams is available on request. Current prices and limits are on the plans page, in Singapore dollars.",
            },
            {
              question: "Which sources does SingLaw use?",
              answer:
                "Singapore Statutes Online legislation — Acts and subsidiary legislation, with repealed Acts flagged — Supreme Court judgments and Practice Directions. Agency guidance from MOM, HDB, Customs and PDPC is on the roadmap and is not indexed yet, so SingLaw will not cite it.",
            },
          ].map(({ question, answer }, index) => (
            <AccordionItem value={`faq-${index}`} key={question}>
              <AccordionTrigger>{question}</AccordionTrigger>
              <AccordionContent>{answer}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
        <p className="marketing-faq-note">
          The full picture is short enough to read.{" "}
          <Link to="/terms">
            Read our terms & privacy <ArrowUpRight size={12} />
          </Link>
        </p>
      </Reveal>
    </section>
  );
}
