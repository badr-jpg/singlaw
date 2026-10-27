import { useMemo } from "react";
import { Copy, RotateCcw, ThumbsDown, ThumbsUp } from "lucide-react";
import {
  Message,
  MessageAction,
  MessageActions,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { citesLegislation, renderableAnswer, type UiMessage } from "@/lib/singlaw";
import {
  AnswerStatusRow,
  Attribution,
  FilteredNote,
  HighStakesCard,
  LowConfidenceFrame,
} from "../trust/surfaces";
import { AnswerContext, type SourceRef } from "./answer-context";
import { CiteAnchor } from "./cite-link";
import { RetrievalInspector } from "./retrieval-inspector";

const RESPONSE_COMPONENTS = { a: CiteAnchor };

function answerLabel(message: UiMessage): string {
  const n = message.sources.length;
  const count = `${n} source${n === 1 ? "" : "s"}`;
  if (message.streaming) return n > 0 ? count.toUpperCase() : "ANSWERING";
  if (message.error && !message.text) return "NO ANSWER";
  if (n === 0) return "NO SOURCES CITED";
  if (message.validation && message.validation.grounded === false)
    return `CHECK SOURCES · ${count}`;
  if (message.meta?.low_confidence) return `LOW CONFIDENCE · ${count}`;
  return `GROUNDED · ${count}`;
}

export function AssistantMessage({
  message,
  canRegenerate,
  openSource,
  onCopy,
  onFeedback,
  onRegenerate,
}: {
  message: UiMessage;
  canRegenerate: boolean;
  openSource: (source: SourceRef) => void;
  onCopy: (message: UiMessage) => void;
  onFeedback: (message: UiMessage, rating: "up" | "down") => void;
  onRegenerate: (message: UiMessage) => void;
}) {
  const streaming = !!message.streaming;
  const meta = message.meta;
  const context = useMemo(
    () => ({
      sources: message.sources,
      invalidCites: message.validation?.invalid_cites ?? [],
      openSource,
    }),
    [message.sources, message.validation, openSource],
  );
  const markdown = useMemo(
    () => renderableAnswer(message.text, streaming),
    [message.text, streaming],
  );
  const finished = !streaming;
  const canAct = finished && !!message.text;
  const showAttribution = finished && citesLegislation(message.sources);

  const body = (
    <>
      {markdown ? (
        <AnswerContext.Provider value={context}>
          <MessageResponse
            className="singlaw-response"
            isAnimating={streaming}
            components={RESPONSE_COMPONENTS}
          >
            {markdown}
          </MessageResponse>
        </AnswerContext.Provider>
      ) : streaming ? (
        <p className="answer-wait">
          <Shimmer>Reading the law…</Shimmer>
        </p>
      ) : null}
      {message.aborted && <p className="answer-note">Stopped before the answer was complete.</p>}
      {message.error && <p className="answer-error">{message.error}</p>}
    </>
  );

  return (
    <Message from="assistant" className="singlaw-message">
      <div className="assistant-identity">
        <span className="brand-mark" aria-hidden="true">
          §
        </span>{" "}
        SingLaw <span className="answer-label">{answerLabel(message)}</span>
      </div>
      {meta && <HighStakesCard highStakes={meta.high_stakes} />}
      <MessageContent>
        {meta?.low_confidence ? (
          <LowConfidenceFrame reasons={meta.low_confidence_reasons}>{body}</LowConfidenceFrame>
        ) : (
          body
        )}
      </MessageContent>
      {finished && (message.sources.length > 0 || meta || message.validation) && (
        <AnswerStatusRow sources={message.sources} meta={meta} validation={message.validation} />
      )}
      {finished && <FilteredNote filtered={meta?.filtered} />}
      {showAttribution && <Attribution text={meta?.attribution} />}
      {canAct && (
        <MessageActions className="answer-actions">
          <MessageAction tooltip="Copy answer with citations" onClick={() => onCopy(message)}>
            <Copy size={13} />
          </MessageAction>
          <MessageAction
            tooltip="Helpful"
            aria-pressed={message.feedback === "up"}
            data-active={message.feedback === "up" || undefined}
            onClick={() => onFeedback(message, "up")}
          >
            <ThumbsUp size={13} />
          </MessageAction>
          <MessageAction
            tooltip="Not helpful"
            aria-pressed={message.feedback === "down"}
            data-active={message.feedback === "down" || undefined}
            onClick={() => onFeedback(message, "down")}
          >
            <ThumbsDown size={13} />
          </MessageAction>
          {canRegenerate && (
            <MessageAction tooltip="Regenerate answer" onClick={() => onRegenerate(message)}>
              <RotateCcw size={13} />
            </MessageAction>
          )}
        </MessageActions>
      )}
      {finished && !message.error && message.question && (
        <RetrievalInspector
          question={message.question}
          docIds={message.docIds ?? null}
          businessId={message.meta?.business_id ?? null}
          answerTimings={message.timings}
          openSource={openSource}
        />
      )}
    </Message>
  );
}
