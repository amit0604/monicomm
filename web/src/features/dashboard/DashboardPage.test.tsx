import { fireEvent, render, screen, within } from "@testing-library/react";
import { I18nProvider } from "../../i18n";
import { DashboardPage } from "./DashboardPage";

const device = {
  id: "d1",
  name: "DEMO-sw-1",
  ip: "192.0.2.1",
  vendor: "Cisco",
  model: null,
  type: "switch",
  status: "critical",
  os_version: null,
  serial: null,
  site: null,
  last_poll_at: null,
};
const event = {
  id: "e1",
  kind: "syslog",
  severity: "crit",
  severity_group: "critical",
  device_id: "d1",
  device_name: "DEMO-sw-1",
  source_ip: "192.0.2.1",
  received_at: new Date().toISOString(),
  message: "link down",
};
const noMetrics = { cpu_pct: null, memory_pct: 50, temperature_c: null, uptime_seconds: null };
const by_status = { online: 0, warning: 0, critical: 1, suspected_offline: 0, offline: 0 };

function reply(url: string): unknown {
  if (url.includes("/summary"))
    return {
      source: "demo",
      devices: { total: 1, by_status },
      open_alerts: [],
      recent_events: [event],
    };
  if (url.includes("/devices/d1"))
    return {
      source: "demo",
      device: { ...device, interfaces: [], metrics: noMetrics },
      events: [event],
    };
  if (url.includes("/devices")) {
    const items = url.includes("q=zzz") ? [] : [device];
    return { source: "demo", total: 1, vendors: ["Cisco"], items };
  }
  return { source: "demo", total: 1, items: [event] };
}

const ok = (url: string) => Promise.resolve(new Response(JSON.stringify(reply(url))));
const fetchMock = vi.fn(ok);

beforeEach(() => {
  localStorage.setItem("lang", "en");
  fetchMock.mockReset().mockImplementation(ok);
  vi.stubGlobal("fetch", fetchMock);
  render(
    <I18nProvider>
      <DashboardPage />
    </I18nProvider>,
  );
});
afterEach(() => vi.unstubAllGlobals());

const tab = (name: string) =>
  within(screen.getByRole("navigation", { name: "Dashboard sections" })).getByRole("button", {
    name,
  });

describe("DashboardPage", () => {
  it("labels demo data and shows the counts", async () => {
    expect(await screen.findByText("DEMO")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Total devices/ })).toHaveTextContent("1");
  });

  it("opens device details from the table and shows missing values as missing", async () => {
    fireEvent.click(tab("Devices"));
    fireEvent.click(await screen.findByRole("button", { name: "DEMO-sw-1" }));
    expect(await screen.findByText("Device information")).toBeInTheDocument();
    expect(screen.getAllByText("No data")).toHaveLength(3);
    expect(screen.getByText("Unassigned")).toBeInTheDocument();
  });

  it("opens the device list filtered from a status row", async () => {
    fireEvent.click(await screen.findByTitle("Critical: 1 (100%)"));
    await screen.findByRole("button", { name: "DEMO-sw-1" });
    expect(fetchMock.mock.lastCall?.[0]).toContain("status=critical");
  });

  it("searches, shows the empty state and clears", async () => {
    fireEvent.click(tab("Devices"));
    await screen.findByRole("button", { name: "DEMO-sw-1" });
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "zzz" } });
    expect(await screen.findByText("No results")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Clear filters" })[0]);
    expect(await screen.findByRole("button", { name: "DEMO-sw-1" })).toBeInTheDocument();
  });

  it("filters events by severity", async () => {
    fireEvent.click(tab("Events"));
    await screen.findByText("link down");
    fireEvent.change(screen.getByLabelText("All severities"), { target: { value: "critical" } });
    await vi.waitFor(() => expect(fetchMock.mock.lastCall?.[0]).toContain("severity=critical"));
  });

  it("shows an error and recovers on retry", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(new Response("{}", { status: 503 })));
    fireEvent.click(tab("Devices"));
    expect(await screen.findByRole("alert")).toHaveTextContent("No data source");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("button", { name: "DEMO-sw-1" })).toBeInTheDocument();
  });
});
