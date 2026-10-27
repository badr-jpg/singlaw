/**
 * Pure pricing/usage helpers for the plans page. Prices always come from
 * `api.plans()`; nothing here hardcodes an amount.
 */
import type { BillingStatus, Plan } from "@/lib/api";

export type BillingInterval = "monthly" | "yearly";

export function formatSgd(amount: number): string {
  const whole = Number.isInteger(amount);
  return `S$${amount.toLocaleString("en-SG", {
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: whole ? 0 : 2,
  })}`;
}

/** "S$29 / month", "S$290 / year", free → "S$0", unpriced → "Talk to us". */
export function formatPrice(amount: number | null, interval: BillingInterval): string {
  if (amount === null) return "Talk to us";
  if (amount === 0) return "S$0";
  return `${formatSgd(amount)} / ${interval === "monthly" ? "month" : "year"}`;
}

export function isFreePlan(plan: Pick<Plan, "price_monthly_sgd" | "price_yearly_sgd">): boolean {
  return plan.price_monthly_sgd === 0 || plan.price_yearly_sgd === 0;
}

export interface PlanPrice {
  label: string;
  /** The interval the label is actually priced at (null when unpriced). */
  interval: BillingInterval | null;
  note: string | null;
}

/** Price label for a plan at the chosen interval, falling back truthfully when one interval is not offered. */
export function planPrice(
  plan: Pick<Plan, "price_monthly_sgd" | "price_yearly_sgd">,
  interval: BillingInterval,
): PlanPrice {
  if (isFreePlan(plan)) return { label: "S$0", interval, note: "Free. No card needed." };
  const monthly = plan.price_monthly_sgd;
  const yearly = plan.price_yearly_sgd;
  const wanted = interval === "monthly" ? monthly : yearly;
  if (wanted !== null) {
    let note: string | null = null;
    if (interval === "yearly" && monthly !== null && monthly * 12 > wanted) {
      note = `Save ${formatSgd(monthly * 12 - wanted)} a year`;
    } else if (interval === "monthly" && yearly !== null) {
      note = `or ${formatPrice(yearly, "yearly")}`;
    }
    return { label: formatPrice(wanted, interval), interval, note };
  }
  const other: BillingInterval = interval === "monthly" ? "yearly" : "monthly";
  const fallback = other === "monthly" ? monthly : yearly;
  if (fallback !== null) {
    return {
      label: formatPrice(fallback, other),
      interval: other,
      note: other === "monthly" ? "Billed monthly" : "Billed yearly",
    };
  }
  return { label: "Talk to us", interval: null, note: "Custom pricing" };
}

export type PlanAction = "current" | "free" | "checkout" | "waitlist";

export function planAction(
  plan: Pick<Plan, "id" | "available" | "price_monthly_sgd" | "price_yearly_sgd">,
  currentPlanId: string | null | undefined,
): PlanAction {
  if (currentPlanId && currentPlanId === plan.id) return "current";
  if (isFreePlan(plan)) return "free";
  if (!plan.available) return "waitlist";
  return "checkout";
}

export function formatLimit(limit: number | null): string {
  return limit === null ? "unlimited" : limit.toLocaleString("en-SG");
}

/** 0–1 share of a limit used, or null when the limit is unlimited. */
export function usageRatio(used: number, limit: number | null): number | null {
  if (limit === null || limit <= 0) return null;
  return Math.min(1, Math.max(0, used / limit));
}

export interface UsageRow {
  key: keyof BillingStatus["usage"];
  label: string;
  used: number;
  limit: number | null;
}

export function usageRows(status: Pick<BillingStatus, "usage" | "limits">): UsageRow[] {
  return [
    { key: "conversations", label: "Conversations", used: status.usage.conversations, limit: null },
    { key: "messages", label: "Messages", used: status.usage.messages, limit: null },
    {
      key: "documents",
      label: "Documents",
      used: status.usage.documents,
      limit: status.limits.documents,
    },
    {
      key: "businesses",
      label: "Businesses",
      used: status.usage.businesses,
      limit: status.limits.businesses,
    },
  ];
}

export function limitBadges(limits: Plan["limits"]): string[] {
  return [
    `${formatLimit(limits.documents)} ${limits.documents === 1 ? "document" : "documents"}`,
    `${formatLimit(limits.businesses)} ${limits.businesses === 1 ? "business" : "businesses"}`,
  ];
}
