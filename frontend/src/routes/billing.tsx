import { createFileRoute } from "@tanstack/react-router";
import { PublicLayout } from "@/components/singlaw/shell";
import { metadata } from "@/lib/singlaw";
import {
  Reveal,
  MarketingPlans,
  Benefits,
  MarketingClose,
  SourceMarquee,
  MarketingFAQ,
  BillingSummary,
} from "@/components/singlaw/marketing";
import "@/public.css";

export const Route = createFileRoute("/billing")({
  head: () =>
    metadata(
      "SingLaw plans & billing",
      "A free Personal plan, a paid Business plan and Teams on request. Prices in Singapore dollars, limits shown on every plan, and your current usage at a glance.",
    ),
  component: Billing,
});

function Billing() {
  return (
    <div className="marketing-site">
      <PublicLayout>
        <main>
          <section className="marketing-billing-hero marketing-inner">
            <Reveal>
              <p className="marketing-kicker">SingLaw · Plans & billing</p>
              <h1>
                Clear prices.
                <br />
                <span>Cited answers.</span>
              </h1>
              <p>
                Start free and upgrade when your questions do.
                <br />
                Prices in Singapore dollars, with the limits shown on every plan.
              </p>
            </Reveal>
          </section>
          <MarketingPlans />
          <Benefits />
          <SourceMarquee />
          <BillingSummary />
          <MarketingFAQ />
          <MarketingClose />
        </main>
      </PublicLayout>
    </div>
  );
}
