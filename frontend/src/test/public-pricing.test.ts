import { describe, expect, it } from "vitest";
import {
  formatLimit,
  formatPrice,
  isFreePlan,
  limitBadges,
  planAction,
  planPrice,
  usageRatio,
  usageRows,
} from "@/components/singlaw/explorer/pricing";

describe("Plan pricing", () => {
  it("formats prices from the API without inventing any", () => {
    expect(formatPrice(29, "monthly")).toBe("S$29 / month");
    expect(formatPrice(290, "yearly")).toBe("S$290 / year");
    expect(formatPrice(1290, "yearly")).toBe("S$1,290 / year");
    expect(formatPrice(9.5, "monthly")).toBe("S$9.50 / month");
    expect(formatPrice(0, "monthly")).toBe("S$0");
    expect(formatPrice(null, "yearly")).toBe("Talk to us");
  });

  it("prices a plan at the chosen interval and says so when it falls back", () => {
    const business = { price_monthly_sgd: 29, price_yearly_sgd: 290 };
    expect(planPrice(business, "monthly")).toEqual({
      label: "S$29 / month",
      interval: "monthly",
      note: "or S$290 / year",
    });
    expect(planPrice(business, "yearly")).toEqual({
      label: "S$290 / year",
      interval: "yearly",
      note: "Save S$58 a year",
    });
    expect(planPrice({ price_monthly_sgd: 29, price_yearly_sgd: null }, "yearly")).toEqual({
      label: "S$29 / month",
      interval: "monthly",
      note: "Billed monthly",
    });
    expect(planPrice({ price_monthly_sgd: 0, price_yearly_sgd: 0 }, "yearly").label).toBe("S$0");
    expect(planPrice({ price_monthly_sgd: null, price_yearly_sgd: null }, "monthly")).toEqual({
      label: "Talk to us",
      interval: null,
      note: "Custom pricing",
    });
  });

  it("picks the right call to action", () => {
    const personal = { id: "personal", available: true, price_monthly_sgd: 0, price_yearly_sgd: 0 };
    const business = {
      id: "business",
      available: true,
      price_monthly_sgd: 29,
      price_yearly_sgd: 290,
    };
    const teams = {
      id: "teams",
      available: false,
      price_monthly_sgd: null,
      price_yearly_sgd: null,
    };
    expect(isFreePlan(personal)).toBe(true);
    expect(planAction(personal, "business")).toBe("free");
    expect(planAction(business, "personal")).toBe("checkout");
    expect(planAction(business, "business")).toBe("current");
    expect(planAction(teams, null)).toBe("waitlist");
  });

  it("describes limits and usage honestly", () => {
    expect(formatLimit(null)).toBe("unlimited");
    expect(formatLimit(50)).toBe("50");
    expect(limitBadges({ businesses: 1, documents: null })).toEqual([
      "unlimited documents",
      "1 business",
    ]);
    expect(usageRatio(5, null)).toBeNull();
    expect(usageRatio(5, 10)).toBe(0.5);
    expect(usageRatio(50, 10)).toBe(1);
    const rows = usageRows({
      usage: { conversations: 4, messages: 20, documents: 2, businesses: 1 },
      limits: { businesses: 3, documents: 10 },
    });
    expect(rows.map((r) => [r.label, r.used, r.limit])).toEqual([
      ["Conversations", 4, null],
      ["Messages", 20, null],
      ["Documents", 2, 10],
      ["Businesses", 1, 3],
    ]);
  });
});
