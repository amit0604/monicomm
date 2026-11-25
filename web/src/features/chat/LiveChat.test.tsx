import { fireEvent, render, screen } from "@testing-library/react";
import { TextProvider } from "../../text";
import { LiveChat } from "./LiveChat";

const counts = { devices: 22, alerts: 7, events: 19 };
const answer = (reply: string) =>
  new Response(
    JSON.stringify({
      source: "demo",
      reply,
      model: "m",
      context: { collected_at: new Date().toISOString(), included: counts, totals: counts },
    }),
  );
const fetchMock = vi.fn();

function open() {
  return render(
    <TextProvider>
      <LiveChat />
    </TextProvider>,
  );
}
function ask(text: string) {
  const box = screen.getByLabelText("Ask a question…");
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: "Enter" });
}

beforeEach(() => {
  localStorage.setItem("lang", "en");
  sessionStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("LiveChat", () => {
  it("shows the question, a loading state, then the answer with sources and demo label", async () => {
    fetchMock.mockResolvedValueOnce(answer("all good"));
    open();
    ask("status?");
    expect(screen.getByText("status?")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("analyzing");
    expect(await screen.findByText("all good")).toBeInTheDocument();
    expect(screen.getByText("DEMO")).toBeInTheDocument();
    expect(screen.getByText("22/22")).toBeInTheDocument();
  });

  it("sends the conversation with a follow-up and keeps it after leaving the page", async () => {
    fetchMock.mockResolvedValueOnce(answer("one")).mockResolvedValueOnce(answer("two"));
    const first = open();
    ask("first");
    await screen.findByText("one");
    ask("second");
    await screen.findByText("two");
    const { messages } = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(messages).toEqual([
      { role: "user", content: "first" },
      { role: "assistant", content: "one" },
      { role: "user", content: "second" },
    ]);
    first.unmount();
    open();
    expect(screen.getByText("two")).toBeInTheDocument();
  });

  it("explains an unavailable model and retries the same question", async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "llm_unavailable" }), { status: 503 }),
      )
      .mockResolvedValueOnce(answer("back"));
    open();
    ask("q");
    expect(await screen.findByRole("alert")).toHaveTextContent("not available");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("back")).toBeInTheDocument();
  });

  it("starts a new chat", async () => {
    fetchMock.mockResolvedValueOnce(answer("one"));
    open();
    ask("first");
    await screen.findByText("one");
    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.queryByText("one")).toBeNull();
  });
});
