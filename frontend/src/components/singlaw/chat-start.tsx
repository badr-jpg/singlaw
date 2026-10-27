import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { Building2, UserRound, Flame, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, type Business } from "@/lib/api";
import { SourceLogo } from "./source-logo";
import { SingaporeFlag } from "./singapore-flag";

type Mode = "personal" | "business";

export function ChatWelcome({
  mode,
  onModeChange,
  business,
}: {
  mode: Mode;
  onModeChange: (mode: Mode) => void;
  business: Business | null;
}) {
  const reduced = useReducedMotion();
  return (
    <div className="chat-width welcome-content enter">
      <div className="welcome-art" aria-hidden="true">
        <svg
          className="welcome-skyline"
          viewBox="0 0 250 70"
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
        >
          <path d="M0 65h250M13 65V43h15v22m4 0V30h13v35m5 0V18h15v47m-12-47V12h9v6m8 47V36h10v29m2 0V27h13v38m68 0V28h13v37m6 0V24h10v41m6 0V28h10v37m-28-45c10-4 29-4 39 0l-2 5h-35l-2-5Zm42 45V41h14v24m5 0V32h10v33" />
          <path
            d="M18 49h5m13-13h5m-5 7h5m-5 7h5m13-26h7m-7 8h7m-7 8h7m111-5h5m-5 8h5m39 5h6"
            opacity=".65"
          />
          <path className="skyline-accent" d="M162 65h55" strokeWidth="2" />
        </svg>
        <span className="welcome-emblem">§</span>
      </div>
      <p className="welcome-kicker">
        <SingaporeFlag /> Your Singapore legal companion
      </p>
      <h1>
        Big questions.<em>A clearer starting point.</em>
      </h1>
      <p className="welcome-subtitle">
        From your first lease to your next business move.
        <br />
        Singapore law, answered with the provisions and judgments behind it.
      </p>
      <div className="mode-control" role="group" aria-label="Question context">
        {(
          [
            { value: "personal", label: "For myself", icon: UserRound },
            { value: "business", label: "For my business", icon: Building2 },
          ] as const
        ).map(({ value, label, icon: Icon }) => (
          <Button
            key={value}
            variant="ghost"
            data-active={mode === value}
            aria-pressed={mode === value}
            onClick={() => onModeChange(value)}
          >
            {mode === value && (
              <motion.span
                className="mode-highlight"
                layoutId="question-context"
                transition={
                  reduced ? { duration: 0 } : { type: "spring", stiffness: 400, damping: 32 }
                }
              />
            )}
            <Icon className="size-3" />
            {label}
          </Button>
        ))}
      </div>
      {mode === "business" && (
        <p className="business-hint">
          {business
            ? `Answers will draw on ${business.name}'s ${business.document_count} document${
                business.document_count === 1 ? "" : "s"
              } alongside Singapore law.`
            : "Add or select a business in the sidebar to bring its documents into the conversation."}
        </p>
      )}
    </div>
  );
}

export function PromptSuggestions({
  mode,
  choosePrompt,
  disabled,
}: {
  mode: Mode;
  choosePrompt: (text: string) => void;
  disabled: boolean;
}) {
  const reduced = useReducedMotion();
  const query = useQuery({
    queryKey: ["suggestions", mode],
    queryFn: () => api.suggestions(mode),
    staleTime: 5 * 60_000,
    retry: 1,
  });
  const items = query.data?.suggestions ?? [];
  if (query.isError || items.length === 0) return null;
  return (
    <div className="composer-suggestions">
      <div className="suggestions-heading">
        <span>
          <Flame size={12} /> Trending questions
        </span>
      </div>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={mode}
          className="trending-questions"
          initial={{ opacity: 0, y: reduced ? 0 : 5 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: reduced ? 0 : -5 }}
          transition={{ duration: reduced ? 0 : 0.16 }}
        >
          {items.map((s) => (
            <button
              className="trending-question"
              key={s.text}
              disabled={disabled}
              title={s.label}
              onClick={() => choosePrompt(s.text)}
            >
              <TrendingUp aria-hidden="true" />
              <span>{s.text}</span>
            </button>
          ))}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

export function WorkspaceSources() {
  return (
    <div className="workspace-sources">
      <span>Explore official references</span>
      {[
        { id: "sso", name: "SG Statutes" },
        { id: "courts", name: "Singapore Courts" },
        { id: "mom", name: "MOM" },
        { id: "hdb", name: "HDB" },
        { id: "customs", name: "Singapore Customs" },
      ].map(({ id, name }) => (
        <Link key={id} to="/sources">
          <SourceLogo id={id} />
          {name}
        </Link>
      ))}
    </div>
  );
}
