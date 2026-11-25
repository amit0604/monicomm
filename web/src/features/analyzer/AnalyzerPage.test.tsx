import { fireEvent, render, screen, within } from "@testing-library/react";
import { I18nProvider } from "../../i18n";
import { AnalyzerPage } from "./AnalyzerPage";
import type { Report, ReportSummary, Topology } from "./api";

const B = "/api/v1/analyzer/impact";

const TOPO: Topology = {
  source: "demo",
  as_of: "2026-11-25T10:00:00Z",
  nodes: [
    {
      id: "DEMO-core-sw-01",
      type: "switch",
      role: "core",
      vendor: "Cisco",
      site: "Site A",
      interfaces: ["GigabitEthernet1/0/1", "GigabitEthernet1/0/2"],
      endpoints: 0,
      services: [],
    },
    {
      id: "DEMO-acc-sw-01",
      type: "switch",
      role: "access",
      vendor: "Cisco",
      site: "Site A",
      interfaces: ["Gi0/1"],
      endpoints: 40,
      services: [],
    },
  ],
  links: [],
};

const REPORT: Report = {
  id: "imp-20261125-ab12cd",
  created_at: "2026-11-25T10:05:00Z",
  source: "demo",
  data_as_of: "2026-11-25T10:00:00Z",
  change: { kind: "interface_down", device: "DEMO-core-sw-01", interface: "GigabitEthernet1/0/1" },
  title: "Shut GigabitEthernet1/0/1 on DEMO-core-sw-01",
  risk: "high",
  summary: "2 devices lose connectivity; L4 goes to 104% after reroute.",
  affected: [
    {
      kind: "node",
      id: "DEMO-acc-sw-01",
      label: "DEMO-acc-sw-01",
      detail: "loses connectivity to core",
      status: "critical",
    },
    { kind: "link", id: "L7", label: "L7", detail: "utilization unknown", status: "neutral" },
  ],
  reroutes: [
    {
      link: "L1",
      via: ["L2", "L4"],
      load_mbps: 4150,
      after: [{ link: "L4", label: "core-sw-02 ↔ dist-sw-01", util_before: 40, util_after: 81.5 }],
    },
  ],
  new_spofs: [{ kind: "link", id: "L4", label: "core-sw-02 ↔ dist-sw-01" }],
  maintenance_window: { start_hour: 3, end_hour: 4, avg_util_pct: 4.2 },
  rollback: "interface GigabitEthernet1/0/1\n no shutdown",
  warnings: [],
  unknowns: ["utilization of L7 not polled"],
  data_used: ["demo topology as of 2026-11-25T10:00:00Z"],
};

const SUMMARY: ReportSummary = {
  id: "imp-old",
  created_at: "2026-11-24T09:00:00Z",
  title: "Reboot DEMO-acc-sw-01",
  risk: "medium",
  source: "demo",
};

type Routes = Record<string, (body?: unknown) => [number, unknown]>;

function stubFetch(routes: Routes) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const route = routes[`${init?.method ?? "GET"} ${url}`];
    if (!route) return new Response("{}", { status: 404 });
    const [status, body] = route(init?.body ? JSON.parse(String(init.body)) : undefined);
    return new Response(JSON.stringify(body), { status });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const base: Routes = {
  [`GET ${B}/topology`]: () => [200, TOPO],
  [`GET ${B}/reports`]: () => [200, []],
};

function renderPage() {
  return render(
    <I18nProvider locale="en">
      <AnalyzerPage />
    </I18nProvider>,
  );
}

const select = (name: string) => screen.getByRole("combobox", { name }) as HTMLSelectElement;

afterEach(() => vi.unstubAllGlobals());

describe("AnalyzerPage", () => {
  it("builds the form from the topology", async () => {
    stubFetch(base);
    renderPage();
    expect(screen.getByRole("status", { name: "Loading topology" })).toBeInTheDocument();

    const device = await screen.findByRole("combobox", { name: "Device" });
    expect(within(device).getByRole("option", { name: "DEMO-core-sw-01" })).toBeInTheDocument();
    fireEvent.change(device, { target: { value: "DEMO-core-sw-01" } });
    expect(
      within(select("Interface")).getByRole("option", { name: "GigabitEthernet1/0/2" }),
    ).toBeInTheDocument();

    fireEvent.change(select("Action"), { target: { value: "device_down" } });
    expect(screen.queryByRole("combobox", { name: "Interface" })).toBeNull();
    expect(screen.getByText("Simulation only. Nothing is sent to devices.")).toBeInTheDocument();
    expect(await screen.findByText("No saved reports yet")).toBeInTheDocument();
  });

  it("simulates a change and shows the risk and reroutes", async () => {
    const post = vi.fn(() => [201, REPORT] as [number, unknown]);
    stubFetch({ ...base, [`POST ${B}/reports`]: post });
    renderPage();

    fireEvent.change(await screen.findByRole("combobox", { name: "Device" }), {
      target: { value: "DEMO-core-sw-01" },
    });
    const simulate = screen.getByRole("button", { name: "Simulate impact" });
    expect(simulate).toBeDisabled();
    fireEvent.change(select("Interface"), { target: { value: "GigabitEthernet1/0/1" } });
    fireEvent.click(simulate);

    const report = await screen.findByRole("article", { name: REPORT.title });
    expect(post).toHaveBeenCalledWith({
      change: {
        kind: "interface_down",
        device: "DEMO-core-sw-01",
        interface: "GigabitEthernet1/0/1",
      },
    });
    expect(within(report).getByText("High risk")).toBeInTheDocument();
    expect(within(report).getByText("DEMO")).toBeInTheDocument();
    expect(within(report).getByText("Unknown")).toBeInTheDocument();
    const row = within(report).getByRole("row", { name: /L1/ });
    expect(row).toHaveTextContent("L2 → L4");
    expect(row).toHaveTextContent("40.0%");
    expect(within(row).getByText("81.5%")).toBeInTheDocument();
    expect(within(report).getByText("03:00–04:00, avg 4.2%")).toBeInTheDocument();
    expect(
      within(report).getByRole("heading", {
        name: "Not visible to Monicomm — not safe by default",
      }),
    ).toBeInTheDocument();
  });

  it("Understand fills the form from free text and marks it as AI", async () => {
    stubFetch({
      ...base,
      [`POST ${B}/parse`]: () => [
        200,
        {
          change: {
            kind: "interface_down",
            device: "DEMO-core-sw-01",
            interface: "GigabitEthernet1/0/2",
          },
        },
      ],
    });
    renderPage();
    fireEvent.change(await screen.findByRole("textbox", { name: "Describe the change" }), {
      target: { value: "shut gi1/0/2 on core 1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Understand" }));

    expect(await screen.findByText(/Check it before simulating/)).toBeInTheDocument();
    expect(screen.getByText("AI")).toBeInTheDocument();
    expect(select("Device").value).toBe("DEMO-core-sw-01");
    expect(select("Interface").value).toBe("GigabitEthernet1/0/2");
    expect(screen.getByRole("button", { name: "Simulate impact" })).toBeEnabled();
  });

  it("shows the parse reason on 422 and a model-down hint on 503", async () => {
    let code = 422;
    stubFetch({
      ...base,
      [`POST ${B}/parse`]: () => [code, { detail: "no device named core-9" }],
    });
    renderPage();
    fireEvent.change(await screen.findByRole("textbox", { name: "Describe the change" }), {
      target: { value: "reboot core-9" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Understand" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not understand the change: no device named core-9",
    );

    code = 503;
    fireEvent.click(screen.getByRole("button", { name: "Understand" }));
    expect(
      await screen.findByText("Local AI model unavailable. Use the form."),
    ).toBeInTheDocument();
  });

  it("shows a friendly state when no topology source is connected", async () => {
    stubFetch({ ...base, [`GET ${B}/topology`]: () => [503, { detail: "no_data_source" }] });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("No topology source connected");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("opens a saved report from the list", async () => {
    stubFetch({
      ...base,
      [`GET ${B}/reports`]: () => [200, [SUMMARY]],
      [`GET ${B}/reports/imp-old`]: () => [200, { ...REPORT, id: "imp-old", title: SUMMARY.title }],
    });
    renderPage();
    const row = await screen.findByRole("button", { name: /Reboot DEMO-acc-sw-01/ });
    expect(row).toHaveTextContent("Medium risk");
    fireEvent.click(row);
    expect(await screen.findByRole("article", { name: SUMMARY.title })).toBeInTheDocument();
    expect(row).toHaveAttribute("aria-current", "true");
  });

  it("shows an error with retry when the report fails", async () => {
    let fail = true;
    stubFetch({
      ...base,
      [`GET ${B}/reports`]: () => [200, [SUMMARY]],
      [`GET ${B}/reports/imp-old`]: () => (fail ? [500, {}] : [200, REPORT]),
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Reboot DEMO-acc-sw-01/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not produce the report.");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("article", { name: REPORT.title })).toBeInTheDocument();
  });
});
