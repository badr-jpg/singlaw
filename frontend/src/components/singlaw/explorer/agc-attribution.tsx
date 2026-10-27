import { Landmark } from "lucide-react";
import { SSO_URL } from "./attribution";

/**
 * The Attorney-General's Chambers notice, shown wherever legislation text is
 * displayed. Wording mirrors the backend's `AGC_ATTRIBUTION` constant; the SSO
 * URL is rendered as a link.
 */
export function AgcAttribution() {
  return (
    <p className="xp-attribution">
      <Landmark size={15} aria-hidden="true" />
      <span>
        Legislation reproduced here is © Singapore Government and reproduced with the permission of
        the Attorney-General's Chambers under the Singapore Statutes Online terms of use. Check{" "}
        <a href={SSO_URL} target="_blank" rel="noreferrer">
          sso.agc.gov.sg
        </a>{" "}
        for the latest version. Material downloaded from SSO is not an authoritative text: section
        48 of the Interpretation Act 1965 does not apply to it — the Gazette remains the
        authoritative text.
      </span>
    </p>
  );
}
