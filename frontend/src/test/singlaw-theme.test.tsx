import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { setAppearance } from "@/lib/appearance";
import { ThemeMenu } from "@/components/singlaw/theme-menu";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  setAppearance("system");
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});

describe("Workspace appearance", () => {
  it("keeps the selected appearance consistent between navigation and header menus", async () => {
    render(
      <>
        <ThemeMenu />
        <ThemeMenu />
      </>,
    );
    const triggers = screen.getAllByRole("button", { name: "Appearance" });
    fireEvent.keyDown(triggers[0]!, { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitemradio", { name: "Dark" }));
    await waitFor(() => expect(document.documentElement).toHaveClass("dark"));
    fireEvent.keyDown(triggers[1]!, { key: "Enter" });
    expect(await screen.findByRole("menuitemradio", { name: "Dark" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });
  it("keeps an appearance change for the session when storage is full", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Quota exceeded", "QuotaExceededError");
    });
    render(<ThemeMenu />);
    fireEvent.keyDown(screen.getByRole("button", { name: "Appearance" }), { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitemradio", { name: "Dark" }));
    await waitFor(() => expect(document.documentElement).toHaveClass("dark"));
  });
  it("preserves a session appearance when another tab updates unrelated storage", async () => {
    setAppearance("light");
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Quota exceeded", "QuotaExceededError");
    });
    render(<ThemeMenu />);
    fireEvent.keyDown(screen.getByRole("button", { name: "Appearance" }), { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitemradio", { name: "Dark" }));
    await waitFor(() => expect(document.documentElement).toHaveClass("dark"));
    fireEvent(
      window,
      new StorageEvent("storage", {
        key: "singlaw.history",
        newValue: "[]",
        storageArea: localStorage,
      }),
    );
    expect(document.documentElement).toHaveClass("dark");
  });
});
