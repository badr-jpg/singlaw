import type { ComponentType, ReactNode } from "react";
import { AlertCircle, BookOpen, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "./errors";

export function ExplorerEmpty({
  icon: Icon = BookOpen,
  title,
  children,
  action,
}: {
  icon?: ComponentType<{ size?: number; strokeWidth?: number }>;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="library-empty enter">
      <Icon size={28} strokeWidth={1.3} />
      <strong>{title}</strong>
      {children}
      {action}
    </div>
  );
}

export function ExplorerError({
  title = "That didn't load",
  error,
  retry,
}: {
  title?: string;
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div className="library-empty xp-error enter" role="alert">
      <AlertCircle size={28} strokeWidth={1.3} />
      <strong>{title}</strong>
      <p>{errorMessage(error)}</p>
      {retry && (
        <Button variant="outline" size="sm" onClick={retry}>
          <RefreshCw /> Try again
        </Button>
      )}
    </div>
  );
}

/** Placeholder cards for the document grid while the table of contents loads. */
export function CardSkeletons({ count = 6 }: { count?: number }) {
  return (
    <div className="library-grid" aria-busy="true" aria-label="Loading documents">
      {Array.from({ length: count }, (_, i) => (
        <article className="source-card xp-skeleton" key={i} aria-hidden="true">
          <i />
          <i />
          <i />
          <i />
        </article>
      ))}
    </div>
  );
}

export function LinesSkeleton({
  lines = 7,
  label = "Loading",
}: {
  lines?: number;
  label?: string;
}) {
  return (
    <div className="xp-lines" aria-busy="true" aria-label={label}>
      {Array.from({ length: lines }, (_, i) => (
        <i key={i} aria-hidden="true" />
      ))}
    </div>
  );
}
