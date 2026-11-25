import { fireEvent, render, screen } from "@testing-library/react";
import { I18nProvider } from "../../i18n";
import { AdminPage } from "./AdminPage";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const view = {
  provider: "gemini",
  base_url: "http://llm:11434",
  model: "qwen2.5:7b",
  gemini_model: "gemini-2.5-flash",
  key_source: "none",
  saved: false,
};
let replies: Record<string, () => Response>;
const fetchMock = vi.fn(async (url: string, init?: RequestInit) =>
  replies[url.endsWith("/test") ? "TEST" : (init?.method ?? "GET")](),
);

beforeEach(() => {
  localStorage.setItem("lang", "en");
  fetchMock.mockClear();
  replies = { GET: () => json(view) };
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function open() {
  render(
    <I18nProvider>
      <AdminPage />
    </I18nProvider>,
  );
}
const typeKey = async () =>
  fireEvent.change(await screen.findByLabelText("API key"), { target: { value: " k-1 " } });
const click = (name: string) => fireEvent.click(screen.getByRole("button", { name }));
const sent = () => JSON.parse(String(fetchMock.mock.lastCall?.[1]?.body));

describe("AdminPage", () => {
  it("saves the key, hides it, and empties the field", async () => {
    replies.PUT = () => json({ ...view, key_source: "saved", saved: true });
    open();
    await typeKey();
    expect(screen.getByLabelText("API key")).toHaveAttribute("type", "password");
    click("Save");
    expect(await screen.findByText(/Saved\. Chat AI/)).toBeInTheDocument();
    expect(sent().api_key).toBe("k-1");
    expect(screen.getByLabelText("API key")).toHaveValue("");
    expect(screen.getByText("Key saved here")).toBeInTheDocument();
  });

  it.each([
    [{ ok: true, error: null }, /Connected/],
    [{ ok: false, error: "key_rejected" }, /Check the API key/],
  ])("shows the connection test result %j", async (result, text) => {
    replies.TEST = () => json(result);
    open();
    await typeKey();
    click("Test connection");
    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it("explains a refused address for the local model", async () => {
    replies.PUT = () => json({ detail: "external_url" }, 400);
    open();
    fireEvent.change(await screen.findByLabelText("AI provider"), { target: { value: "ollama" } });
    expect(screen.queryByLabelText("API key")).toBeNull();
    click("Save");
    expect(await screen.findByRole("alert")).toHaveTextContent("closed network");
    expect(sent()).toMatchObject({ provider: "ollama", api_key: null });
  });

  it("deletes the saved settings after confirming", async () => {
    replies.GET = () => json({ ...view, key_source: "saved", saved: true });
    replies.DELETE = () => json(view);
    vi.stubGlobal("confirm", () => true);
    open();
    await screen.findByLabelText("API key");
    click("Delete saved settings");
    expect(await screen.findByText(/Using \.env/)).toBeInTheDocument();
    expect(screen.getByText("No key set")).toBeInTheDocument();
  });

  it("tells a user without access to sign in", async () => {
    replies.GET = () => json({ detail: "login_off" }, 403);
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign in as an admin");
  });
});
