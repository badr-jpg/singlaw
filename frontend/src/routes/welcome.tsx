import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { PublicLayout } from "@/components/singlaw/shell";
import { Button } from "@/components/ui/button";
import { metadata } from "@/lib/singlaw";
import { SingaporeFlag } from "@/components/singlaw/singapore-flag";
import {
  Reveal,
  ProductPreview,
  SourceMarquee,
  Benefits,
  MarketingPlans,
  MarketingClose,
  HowItWorks,
  MarketingFAQ,
} from "@/components/singlaw/marketing";
import "@/public.css";

export const Route = createFileRoute("/welcome")({
  head: () =>
    metadata(
      "Meet SingLaw — Singapore law, cited and current",
      "Plain-English answers about Singapore law for residents and small businesses, retrieved from Singapore Statutes Online, Supreme Court judgments and Practice Directions — every sentence cited, every answer dated.",
    ),
  component: Welcome,
});

function Welcome() {
  return (
    <div className="marketing-site">
      <PublicLayout>
        <main>
          <section className="marketing-hero marketing-inner">
            <Reveal>
              <p className="marketing-hero-eyebrow">
                <SingaporeFlag /> Singapore law, cited and current
              </p>
              <h1>
                Singapore law.
                <br />
                <em>Answered with the source.</em>
              </h1>
              <p className="marketing-hero-copy">
                Ask about your lease, your contract or the business you run — in plain English.
                <br />
                SingLaw answers from the Acts, regulations and judgments themselves, with a citation
                on every sentence.
              </p>
              <div className="marketing-hero-actions">
                <Button asChild size="lg">
                  <Link to="/">
                    Ask your first question <ArrowRight />
                  </Link>
                </Button>
                <Button asChild variant="link">
                  <Link to="/billing">
                    See the plans <ArrowRight />
                  </Link>
                </Button>
              </div>
            </Reveal>
            <p className="marketing-hero-note">
              Free to start · Every answer cited · Made for Singapore
            </p>
            <ProductPreview />
            <SourceMarquee />
          </section>
          <Benefits />
          <HowItWorks />
          <MarketingPlans />
          <MarketingFAQ />
          <MarketingClose />
        </main>
      </PublicLayout>
    </div>
  );
}
