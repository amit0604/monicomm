import { fireEvent, render, screen } from "@testing-library/react";
import { InvestigatorPage } from "./InvestigatorPage";
import { INCIDENT, stubFetch, SUMMARY } from "./testData";

const LIST = "GET /api/v1/investigator/incidents";
const ONE = `GET /api/v1/investigator/incidents/${SUMMARY.id}`;
const ANALYZE = `POST /api/v1/investigator/incidents/${SUMMARY.id}/analysis`;

afterEach(() => vi.unstubAllGlobals());

describe("InvestigatorPage", () => {
  it("renders incidents grouped by status, with pills and mono devices", async () => {
    stubFetch({
      [LIST]: () => [200, [SUMMARY, { ...SUMMARY, id: "bbbbbbbbbbbb", status: "closed" }]],
    });
    const onSelect = vi.fn();
    render(<InvestigatorPage selectedId={null} onSelect={onSelect} />);
    expect(screen.getByRole("status", { name: "Loading incidents" })).toBeInTheDocument();

    expect(await screen.findByRole("heading", { name: /Open/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Closed/ })).toBeInTheDocument();
    expect(screen.getAllByText("Critical")).toHaveLength(2);
    expect(screen.getAllByText("10.0.0.1, 10.0.0.2")[0]).toHaveClass("mono");

    fireEvent.click(screen.getAllByRole("button", { name: /Link down/ })[0]);
    expect(onSelect).toHaveBeenCalledWith(SUMMARY.id);
  });

  it("shows the empty state when there is nothing abnormal", async () => {
    stubFetch({ [LIST]: () => [200, []] });
    render(<InvestigatorPage selectedId={null} onSelect={() => {}} />);
    expect(
      await screen.findByText("No abnormal events. The network looks normal."),
    ).toBeInTheDocument();
  });

  it("shows an error with retry, and retry loads the list", async () => {
    let fail = true;
    stubFetch({ [LIST]: () => (fail ? [500, {}] : [200, [SUMMARY]]) });
    render(<InvestigatorPage selectedId={null} onSelect={() => {}} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load incidents");

    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(SUMMARY.title)).toBeInTheDocument();
  });

  it("detail shows root cause with confidence, possible causes and impact", async () => {
    stubFetch({ [LIST]: () => [200, [SUMMARY]], [ONE]: () => [200, INCIDENT] });
    render(<InvestigatorPage selectedId={SUMMARY.id} onSelect={() => {}} />);
    expect(await screen.findByText("Gi1/0/24 went down on 10.0.0.1")).toBeInTheDocument();
    expect(screen.getByText("Confidence: high")).toBeInTheDocument();
    expect(screen.getByText("config change on 10.0.0.1 30 s before")).toBeInTheDocument();
    expect(screen.getByText("OSPF adjacency to 10.0.0.1 down")).toBeInTheDocument();
    expect(screen.getByText("Affected")).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Incident details" })).toHaveTextContent(
      "LINK-3-UPDOWN",
    );
  });

  it("shows a friendly message when the local model is down (503)", async () => {
    stubFetch({
      [LIST]: () => [200, [SUMMARY]],
      [ONE]: () => [200, INCIDENT],
      [ANALYZE]: () => [503, { detail: "model unavailable" }],
    });
    render(<InvestigatorPage selectedId={SUMMARY.id} onSelect={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "Analyze with AI" }));
    expect(await screen.findByText(/local model is not available/)).toBeInTheDocument();
  });

  it("shows the AI analysis with an AI tag and sources that highlight timeline rows", async () => {
    stubFetch({
      [LIST]: () => [200, [SUMMARY]],
      [ONE]: () => [200, INCIDENT],
      [ANALYZE]: () => [
        200,
        {
          summary: "The uplink failed.",
          root_cause: "Gi1/0/24 down",
          impact: "OSPF lost",
          sources: ["e1"],
          model: "local",
          created_at: "2026-11-25T10:02:00Z",
        },
      ],
    });
    const { container } = render(<InvestigatorPage selectedId={SUMMARY.id} onSelect={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "Analyze with AI" }));
    expect(await screen.findByText("The uplink failed.")).toBeInTheDocument();
    expect(screen.getByText("AI")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "10.0.0.1 LINK-3-UPDOWN" })).toHaveAttribute(
      "href",
      "#ev-e1",
    );
    expect(container.querySelector("#ev-e1")).toHaveClass("timeline__row--source");
  });

  it("closes an incident via PATCH", async () => {
    const fetchMock = stubFetch({
      [LIST]: () => [200, [SUMMARY]],
      [ONE]: () => [200, INCIDENT],
      [`PATCH /api/v1/investigator/incidents/${SUMMARY.id}`]: () => [200, INCIDENT],
    });
    render(<InvestigatorPage selectedId={SUMMARY.id} onSelect={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "Close incident" }));
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true),
    );
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")!;
    expect(JSON.parse(String(patch[1]?.body))).toEqual({
      notes: "",
      resolution: "",
      status: "closed",
    });
  });
});
