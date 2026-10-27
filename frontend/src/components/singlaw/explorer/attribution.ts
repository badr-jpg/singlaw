/**
 * Verbatim notices mirrored from the backend (`app/schemas.py`). Shown wherever
 * legislation text is displayed and in the terms page.
 */
export const AGC_ATTRIBUTION =
  "Legislation reproduced here is © Singapore Government and reproduced with the permission of the Attorney-General's Chambers under the Singapore Statutes Online terms of use. Check https://sso.agc.gov.sg for the latest version. Material downloaded from SSO is not an authoritative text: section 48 of the Interpretation Act 1965 does not apply to it — the Gazette remains the authoritative text.";

export const LEGAL_INFO_DISCLAIMER =
  "This assistant provides legal information, not legal advice. It explains what the law says; it cannot tell you what to do in your specific situation. For advice on your own matter, consult a lawyer.";

export const SSO_URL = "https://sso.agc.gov.sg";

/** Referral services the assistant surfaces on high-stakes questions (mirrors `app/answer.py`). */
export const HIGH_STAKES_REFERRALS: ReadonlyArray<{ name: string; url: string }> = [
  { name: "Law Society Pro Bono Services", url: "https://www.lawsocprobono.org" },
  { name: "Legal Aid Bureau (MinLaw)", url: "https://lab.mlaw.gov.sg" },
  { name: "Criminal Legal Aid Scheme (CLAS)", url: "https://www.lawsocprobono.org/clas" },
];
