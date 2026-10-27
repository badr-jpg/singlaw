import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SourceLogo, publisherForSource } from "@/components/singlaw/source-logo";

describe("SourceLogo", () => {
  it("renders a local monogram image for known publishers", () => {
    render(<SourceLogo id="sso" />);
    expect(screen.getByRole("presentation", { hidden: true })).toHaveAttribute(
      "src",
      "/sources/sso.svg",
    );
  });
  it("maps judgments and practice directions to the courts publisher", () => {
    expect(publisherForSource("judgment")).toBe("courts");
    expect(publisherForSource("practice_direction")).toBe("courts");
    expect(publisherForSource("act", "https://sso.agc.gov.sg/Act/EmA1968")).toBe("sso");
  });
});
