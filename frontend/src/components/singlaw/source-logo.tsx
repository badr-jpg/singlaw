import { useState } from "react";
import { Landmark, BriefcaseBusiness, House, Package, Scale } from "lucide-react";

/** Publisher monogram tiles shipped locally under public/sources/. */
const LOGOS: Record<string, string> = {
  sso: "/sources/sso.svg",
  mom: "/sources/mom.svg",
  hdb: "/sources/hdb.svg",
  customs: "/sources/customs.svg",
  courts: "/sources/courts.svg",
};

export function publisherForSource(docType: string, url?: string): string {
  if (url?.includes("judiciary.gov.sg") || docType === "judgment") return "courts";
  if (docType === "practice_direction") return "courts";
  return "sso";
}

export function SourceLogo({ id }: { id: string }) {
  const [failed, setFailed] = useState(false);
  const Fallback =
    id === "mom"
      ? BriefcaseBusiness
      : id === "customs"
        ? Package
        : id === "hdb"
          ? House
          : id === "courts"
            ? Scale
            : Landmark;
  const src = LOGOS[id];
  if (failed || !src)
    return (
      <span className="source-logo source-icon-fallback" aria-hidden="true">
        <Fallback />
      </span>
    );
  return (
    <img
      src={src}
      alt=""
      className="source-logo"
      width={14}
      height={14}
      onError={() => setFailed(true)}
    />
  );
}
