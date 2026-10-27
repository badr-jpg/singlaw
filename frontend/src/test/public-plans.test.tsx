import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  RouterProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, type BillingStatus, type Plan } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      plans: vi.fn(),
      billingStatus: vi.fn(),
      checkout: vi.fn(),
      joinWaitlist: vi.fn(),
    },
  };
});

import { api } from "@/lib/api";
import { MarketingPlans } from "@/components/singlaw/marketing";

const plans: Plan[] = [
  {
    id: "personal",
    name: "Personal",
    description: "For everyday questions.",
    price_monthly_sgd: 0,
    price_yearly_sgd: 0,
    features: ["Cited answers"],
    limits: { businesses: 0, documents: 3 },
    featured: false,
    available: true,
  },
  {
    id: "business",
    name: "Business",
    description: "For the company you run.",
    price_monthly_sgd: 29,
    price_yearly_sgd: 290,
    features: ["Document analysis"],
    limits: { businesses: 3, documents: 50 },
    featured: true,
    available: true,
  },
  {
    id: "teams",
    name: "Teams",
    description: "For more than one of you.",
    price_monthly_sgd: null,
    price_yearly_sgd: null,
    features: ["Shared workspaces"],
    limits: { businesses: null, documents: null },
    featured: false,
    available: false,
  },
];
const status: BillingStatus = {
  plan: "personal",
  usage: { conversations: 1, messages: 2, documents: 0, businesses: 0 },
  limits: { businesses: 0, documents: 3 },
  checkout_available: false,
};

function renderPlans() {
  const rootRoute = createRootRoute();
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: MarketingPlans,
  });
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

beforeAll(() => {
  if (!("IntersectionObserver" in window)) {
    Object.defineProperty(window, "IntersectionObserver", {
      writable: true,
      value: class {
        observe() {}
        unobserve() {}
        disconnect() {}
        takeRecords() {
          return [];
        }
      },
    });
  }
});
beforeEach(() => {
  vi.mocked(api.plans).mockResolvedValue({ plans });
  vi.mocked(api.billingStatus).mockResolvedValue(status);
  vi.mocked(api.checkout).mockReset();
  vi.mocked(api.joinWaitlist).mockReset();
});
afterEach(cleanup);

describe("Plans from the API", () => {
  it("renders real prices and switches to yearly", async () => {
    renderPlans();
    expect(await screen.findByText("S$0")).toBeInTheDocument();
    expect(screen.getByText("S$29 / month")).toBeInTheDocument();
    expect(screen.getByText("Talk to us")).toBeInTheDocument();
    expect(
      screen.getByText("Checkout opens soon — join the waitlist to be first.", { exact: false }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Current plan" })).toBeDisabled();
    fireEvent.click(screen.getByRole("switch", { name: "Yearly billing" }));
    expect(await screen.findByText("S$290 / year")).toBeInTheDocument();
  });

  it("falls back to the waitlist when checkout answers 503", async () => {
    vi.mocked(api.checkout).mockRejectedValue(new ApiError(503, "Checkout is not configured yet"));
    vi.mocked(api.joinWaitlist).mockResolvedValue({ ok: true });
    renderPlans();
    fireEvent.click(await screen.findByRole("button", { name: /Choose Business/ }));
    const dialog = await screen.findByRole("dialog", {
      name: /Be first when Business checkout opens/,
    });
    expect(api.checkout).toHaveBeenCalledWith("business", "monthly");
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "you@example.com" } });
    fireEvent.submit(dialog.querySelector("form")!);
    await waitFor(() =>
      expect(api.joinWaitlist).toHaveBeenCalledWith("you@example.com", "business"),
    );
    expect(await screen.findByText(/You're on the list for Business/)).toBeInTheDocument();
  });

  it("sends unavailable plans straight to the waitlist", async () => {
    renderPlans();
    fireEvent.click(await screen.findByRole("button", { name: /Tell us about your team/ }));
    expect(
      await screen.findByRole("dialog", { name: "Tell us about your team" }),
    ).toBeInTheDocument();
    expect(api.checkout).not.toHaveBeenCalled();
  });
});
