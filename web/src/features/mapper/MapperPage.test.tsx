import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { I18nProvider } from "../../i18n";
import { MapperPage } from "./MapperPage";
import { TOPOLOGY } from "./testData";

// jsdom has no canvas: a stand-in graph engine that records what the page draws and lets the
// tests tap nodes the way a user would.
const graph = vi.hoisted(() => ({
  added: [] as { group: string; data: Record<string, unknown> }[],
  handlers: {} as Record<string, (e: { target: unknown }) => void>,
}));
vi.mock("cytoscape", () => ({
  default: vi.fn(() => {
    const collection = { remove: vi.fn(), select: vi.fn(), unselect: vi.fn(), length: 0 };
    const core = {
      on: vi.fn((event: string, selector: unknown, handler?: (e: { target: unknown }) => void) => {
        if (typeof selector === "string" && handler)
          graph.handlers[`${event} ${selector}`] = handler;
      }),
      style: vi.fn(),
      elements: () => collection,
      getElementById: () => collection,
      add: vi.fn((els: typeof graph.added) => {
        graph.added = els;
        return collection;
      }),
      layout: () => ({ run: vi.fn() }),
      fit: vi.fn(),
      resize: vi.fn(),
      destroy: vi.fn(),
    };
    return core;
  }),
}));

function respond(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

function renderPage() {
  return render(
    <I18nProvider>
      <MapperPage theme="light" />
    </I18nProvider>,
  );
}

const table = () => screen.getByRole("table");
const rows = () => within(table()).getAllByRole("row").slice(1);

beforeEach(() => {
  graph.added = [];
  graph.handlers = {};
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("Mapper page", () => {
  it("labels demo data and draws every device and link, with the port at each end", async () => {
    respond(200, TOPOLOGY);
    renderPage();
    expect(await screen.findByText("Demo data – not a real network")).toBeInTheDocument();
    expect(screen.getByText("5 devices · 3 links")).toBeInTheDocument();

    await waitFor(() => expect(graph.added).toHaveLength(8));
    const edge = graph.added.find((e) => e.data.id === "l1")!;
    expect(edge.data).toMatchObject({
      source: "sw",
      target: "rtr",
      aPort: "Gi1/0/1",
      bPort: "ge-0/0/0",
    });
    // a link that isn't up carries its status as text on the map, not only as a line style
    expect(graph.added.find((e) => e.data.id === "l2")!.data.mark).toBe("✕ Down");
    expect(graph.added.find((e) => e.data.id === "l2")!.data.line).toBe("dotted");
  });

  it("shows a legend with every link type and status, each with text", async () => {
    respond(200, TOPOLOGY);
    renderPage();
    const legend = await screen.findByRole("region", { name: "Legend" });
    for (const name of [
      "Fiber",
      "Copper",
      "Wireless",
      "WAN / VPN",
      "Up",
      "Degraded",
      "Down",
      "Unknown",
    ])
      expect(within(legend).getByText(name)).toBeInTheDocument();
  });

  it("lists links with both ends, type, speed, status and reason", async () => {
    respond(200, TOPOLOGY);
    renderPage();
    await screen.findByRole("table");
    expect(rows()).toHaveLength(3);
    const down = rows()[1];
    expect(down).toHaveTextContent("sw-1");
    expect(down).toHaveTextContent("Gi1/0/2");
    expect(down).toHaveTextContent("srv-1");
    expect(down).toHaveTextContent("eth0");
    expect(down).toHaveTextContent("Copper");
    expect(down).toHaveTextContent("1 Gb/s");
    expect(down).toHaveTextContent("Down");
    expect(down).toHaveTextContent("A device on this link is offline");
  });

  it("filters by link type and by status", async () => {
    respond(200, TOPOLOGY);
    renderPage();
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Fiber", pressed: true }));
    expect(rows()).toHaveLength(2);
    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), {
      target: { value: "degraded" },
    });
    expect(rows()).toHaveLength(1);
    expect(rows()[0]).toHaveTextContent("Wireless");
    fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "up" } });
    expect(screen.getByText("No links match these filters.")).toBeInTheDocument();
  });

  it("opens link details from the table, and device details from the link's end", async () => {
    respond(200, TOPOLOGY);
    renderPage();
    await screen.findByRole("table");
    fireEvent.click(within(rows()[2]).getByRole("button"));
    const details = () =>
      screen.getByRole("heading", { level: 2, name: "Details" }).closest("section")!;
    expect(details()).toHaveTextContent("Reported by the link's controller");
    expect(details()).toHaveTextContent("867 Mb/s");

    fireEvent.click(within(details()).getAllByRole("button", { name: /ap-1/ })[0]);
    const device = screen.getByRole("heading", { level: 2, name: "ap-1" }).closest("section")!;
    expect(device).toHaveTextContent("Access point");
    expect(device).toHaveTextContent("Radio1");
    expect(device).toHaveTextContent("rtr-1");
  });

  it("taps on the map select a device, and a device with no links says so", async () => {
    respond(200, TOPOLOGY);
    renderPage();
    await screen.findByRole("table");
    act(() => graph.handlers["tap node"]({ target: { id: () => "lonely" } }));
    const device = screen.getByRole("heading", { level: 2, name: "lonely-1" }).closest("section")!;
    expect(device).toHaveTextContent("No known links");
    fireEvent.click(within(device).getByRole("button", { name: "Close details" }));
    expect(screen.getByText(/Select a device or a link/)).toBeInTheDocument();
  });

  it("says when no data source is connected, and retries", async () => {
    respond(503, { detail: "no_data_source" });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("No data source is connected");
    respond(200, TOPOLOGY);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("treats a reply that isn't a topology as a failure", async () => {
    respond(200, []);
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the network map");
  });

  it("warns about links to devices that are not in the inventory", async () => {
    respond(200, { ...TOPOLOGY, unresolved_links: 2 });
    renderPage();
    expect(
      await screen.findByText(/2 links point to devices that are not in the inventory/),
    ).toBeInTheDocument();
  });
});
