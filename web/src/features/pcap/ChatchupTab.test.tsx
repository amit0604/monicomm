import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../../App";

// jsdom has no canvas: replace the graph engine with a stub that records calls.
const cy = { destroy: vi.fn() };
vi.mock("cytoscape", () => ({
  default: vi.fn(() => ({
    ...cy,
    on: vi.fn(),
    style: vi.fn(),
    elements: () => ({ remove: vi.fn() }),
    add: vi.fn(),
    layout: () => ({ run: vi.fn() }),
    fit: vi.fn(),
    resize: vi.fn(),
  })),
}));

describe("Chatchup tab", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })),
    );
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("mounts inside the shell and lists captures from the pcap API", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Chatchup" }));

    expect(screen.getByRole("button", { name: "Upload capture" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /drop a \.pcap/i })).toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/pcap/captures", {}));
    expect(await screen.findByRole("option", { name: "No captures yet" })).toBeInTheDocument();
  });

  it("cleans up when leaving the tab", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Chatchup" }));
    fireEvent.click(screen.getByRole("button", { name: "Mapper" }));

    expect(cy.destroy).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Upload capture" })).not.toBeInTheDocument();
  });
});
