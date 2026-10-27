import { useContext, type ReactNode } from "react";
import { FileText } from "lucide-react";
import { citeNumberFromHref, problemSeverity } from "@/lib/singlaw";
import { SourceLogo, publisherForSource } from "../source-logo";
import { AnswerContext } from "./answer-context";

export function CitationChip({ n }: { n: number }) {
  const { sources, invalidCites, openSource } = useContext(AnswerContext);
  const source = sources.find((s) => s.n === n);
  if (!source) {
    return (
      <span className="cite-missing" title="source not found">
        [{n}]
      </span>
    );
  }
  const severity = problemSeverity(source.status, source.treatment);
  const invalid = invalidCites.includes(n);
  const userDoc = source.collection === "user_docs";
  return (
    <button
      type="button"
      className="cite-chip"
      data-severity={severity ?? undefined}
      data-invalid={invalid || undefined}
      title={`${source.citation} — open the source`}
      aria-label={`Open source: ${source.citation}`}
      onClick={() => openSource(source)}
    >
      {userDoc ? (
        <FileText className="cite-chip-doc" aria-hidden="true" />
      ) : (
        <SourceLogo id={publisherForSource(source.doc_type, source.url)} />
      )}
      <span className="cite-chip-text">{source.citation}</span>
      {severity && (
        <span className="cite-chip-mark" aria-hidden="true">
          !
        </span>
      )}
    </button>
  );
}

/**
 * Markdown `a` override: `[3](#cite-3)` becomes a citation chip; any other
 * link stays an ordinary external link.
 */
export function CiteAnchor({
  href,
  children,
  node: _node,
  ...rest
}: {
  href?: string | undefined;
  children?: ReactNode;
  node?: unknown;
  className?: string | undefined;
}) {
  const n = citeNumberFromHref(href);
  if (n !== null) return <CitationChip n={n} />;
  return (
    <a {...rest} href={href} className="answer-link" target="_blank" rel="noreferrer">
      {children}
    </a>
  );
}
