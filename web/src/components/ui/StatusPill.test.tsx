import { render, screen } from "@testing-library/react";
import { StatusPill } from "./StatusPill";

describe("StatusPill", () => {
  it("always shows a text label and an icon, not color alone", () => {
    const { container } = render(<StatusPill status="critical" label="Down" />);
    expect(screen.getByText("Down")).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.firstElementChild).toHaveClass("status-pill--critical");
  });
});
