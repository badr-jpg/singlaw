import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Modal } from "@/components/singlaw/shell";

afterEach(cleanup);

function PlanPreview() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Explore plan</button>
      <button>Outside the dialog</button>
      {open && (
        <Modal title="Plan preview" eyebrow="Preview" close={() => setOpen(false)}>
          <p>No payments are collected.</p>
          <button>Keep exploring</button>
        </Modal>
      )}
    </>
  );
}

describe("SingLaw dialogs", () => {
  it("keeps keyboard focus inside an open preview", async () => {
    render(<PlanPreview />);
    const outside = screen.getByRole("button", { name: "Outside the dialog" });
    fireEvent.click(screen.getByRole("button", { name: "Explore plan" }));
    const dialog = screen.getByRole("dialog", { name: "Plan preview" });
    outside.focus();
    await waitFor(() => expect(dialog).toContainElement(document.activeElement as HTMLElement));
  });

  it("returns focus to the opener after Escape dismisses a preview", async () => {
    render(<PlanPreview />);
    const opener = screen.getByRole("button", { name: "Explore plan" });
    opener.focus();
    fireEvent.click(opener);
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(opener).toHaveFocus());
  });
});
