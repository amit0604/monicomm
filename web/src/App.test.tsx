import { fireEvent, render, screen, within } from "@testing-library/react";
import App from "./App";

describe("App shell", () => {
  it("shows the six modules in the fixed nav order", () => {
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "Modules" });
    const names = within(nav)
      .getAllByRole("button")
      .map((b) => b.textContent);
    expect(names).toEqual([
      "Dashboard",
      "Chat AI",
      "Analyzer",
      "Incident Investigator",
      "Mapper",
      "Chatchup",
    ]);
  });

  it("switches the page title when a module is clicked", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Mapper" }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Mapper");
  });

  it("toggles between light and dark theme", () => {
    render(<App />);
    expect(document.documentElement.dataset.theme).toBe("light");
    fireEvent.click(screen.getByRole("button", { name: /switch to dark theme/i }));
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
