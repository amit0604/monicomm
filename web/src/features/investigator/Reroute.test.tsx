import { render as rtlRender, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { I18nProvider, type LocaleCode } from "../../i18n";
import { formatRate, Reroute } from "./Reroute";
import {
  REROUTE,
  REROUTE_CUT_OFF,
  REROUTE_FLOW,
  REROUTE_UNKNOWN,
  REROUTE_WARNING,
} from "./testData";

const render = (ui: ReactElement, locale: LocaleCode = "en") =>
  rtlRender(<I18nProvider locale={locale}>{ui}</I18nProvider>);

const table = (name: RegExp) => screen.getByRole("table", { name });

beforeEach(() => localStorage.clear()); // the provider remembers the language

describe("Reroute", () => {
  it("shows the predicted path with OK hops, moved load and assumptions", () => {
    render(<Reroute reroute={REROUTE} />);
    expect(screen.getByRole("heading", { name: "Rerouting" })).toBeInTheDocument();
    expect(screen.getByText(/Gi1\/0\/24 <-> 10.0.0.2 ge-0\/0\/1 down/)).toBeInTheDocument();
    expect(screen.getByText("Moved load: 420 Mbps")).toBeInTheDocument();
    const predicted = table(/Predicted path/);
    expect(within(predicted).getAllByText("OK")).toHaveLength(2);
    expect(within(predicted).getByText("42 %")).toBeInTheDocument();
    expect(within(predicted).getAllByText("1 Gbps")).toHaveLength(2);
    expect(screen.queryByRole("table", { name: /Recommended/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Recommendation only/)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Based on" })).toBeInTheDocument();
  });

  it("shows a warning predicted path and the recommended path with why", () => {
    render(<Reroute reroute={REROUTE_WARNING} />);
    const predicted = table(/Predicted path/);
    expect(within(predicted).getByText("Warning")).toBeInTheDocument();
    expect(within(predicted).getByText("Critical")).toBeInTheDocument();
    expect(within(predicted).getByText("120 %")).toBeInTheDocument();
    const bars = predicted.querySelectorAll<HTMLElement>(".reroute-util__bar");
    expect(bars[1].style.width).toBe("100%"); // capped
    expect(within(table(/Recommended path/)).getAllByText("OK")).toHaveLength(3);
    expect(screen.getByText("keeps every link under 80 %")).toBeInTheDocument();
    expect(
      screen.getByText("Recommendation only — apply changes through your normal change process."),
    ).toBeInTheDocument();
  });

  it("says the ends are cut off when there is no path, and lists isolated devices", () => {
    render(<Reroute reroute={REROUTE_CUT_OFF} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "No alternative path: the two ends are cut off",
    );
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cut off from the network" })).toBeInTheDocument();
    expect(screen.getByText("10.0.0.9")).toHaveClass("mono");
  });

  it("shows unknown speed and load as Unknown, never OK", () => {
    render(<Reroute reroute={REROUTE_UNKNOWN} />);
    expect(screen.getByText("Moved load: unknown")).toBeInTheDocument();
    const predicted = table(/Predicted path/);
    expect(within(predicted).queryByText("OK")).not.toBeInTheDocument();
    expect(within(predicted).getAllByText("Unknown")).toHaveLength(3); // speed, util, pill
    expect(predicted.querySelector("[data-status]")).toHaveAttribute("data-status", "neutral");
  });

  it("treats a hop with no utilization as unknown even if the server says ok", () => {
    const flow = REROUTE_UNKNOWN.flows[0];
    const hops = flow.predicted!.hops.map((h) => ({ ...h, status: "ok" as const }));
    render(
      <Reroute
        reroute={{
          ...REROUTE_UNKNOWN,
          flows: [{ ...flow, predicted: { ...flow.predicted!, hops } }],
        }}
      />,
    );
    expect(within(table(/Predicted path/)).queryByText("OK")).not.toBeInTheDocument();
  });

  it("describes the path diagram in words", () => {
    render(<Reroute reroute={REROUTE_WARNING} />);
    const img = screen.getByRole("img");
    expect(img.getAttribute("aria-label")).toBe(
      "Path diagram. Before: 10.0.0.1 to 10.0.0.2 (down). " +
        "Predicted: 10.0.0.1 to 10.0.0.4 to 10.0.0.2. " +
        "Recommended: 10.0.0.1 to 10.0.0.3 to 10.0.0.5 to 10.0.0.2.",
    );
  });

  it("draws the diagram at natural size and shortens long names, keeping the full one", () => {
    const long = "core-router-datacenter-north-01";
    const hops = REROUTE_FLOW.before.hops.map((h) => ({ ...h, to: long }));
    render(<Reroute reroute={{ ...REROUTE, flows: [{ ...REROUTE_FLOW, before: { hops } }] }} />);
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("width");
    expect(img.parentElement).toHaveClass("reroute-graph-scroll");
    const label = [...img.querySelectorAll(".reroute-graph__label")].find(
      (el) => el.querySelector("title")?.textContent === long,
    );
    expect(label?.textContent).toBe(`${long}core-router-datac…`); // <title> + 18-char label
  });

  it("renders in Hebrew", () => {
    render(<Reroute reroute={REROUTE_WARNING} />, "he");
    expect(screen.getByRole("heading", { name: "ניתוב מחדש" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /נתיב מומלץ/ })).toBeInTheDocument();
    expect(screen.getByText(/^המלצה בלבד/)).toBeInTheDocument();
    expect(screen.getByText("keeps every link under 80 %")).toBeInTheDocument(); // server text as is
  });

  it("formats rates in human units", () => {
    expect(formatRate(2_500_000_000)).toBe("2.5 Gbps");
    expect(formatRate(1_000_000_000)).toBe("1 Gbps");
    expect(formatRate(420_000_000)).toBe("420 Mbps");
  });
});
