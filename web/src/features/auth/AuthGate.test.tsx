import { fireEvent, render, screen } from "@testing-library/react";
import { I18nProvider } from "../../i18n";
import { AuthGate } from "./AuthGate";
import { useSession } from "./session";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const admin = { name: "admin", role: "admin" };
let me: () => Response;
let sessionReply: () => Response;

const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url.endsWith("/me")) return me();
  if (init?.method === "DELETE") return new Response(null, { status: 204 });
  return sessionReply();
});

beforeEach(() => {
  localStorage.setItem("lang", "en");
  me = () => json({}, 401);
  sessionReply = () => json(admin);
  fetchMock.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function Secret() {
  return <p>secret app {useSession()?.role ?? "no login"}</p>;
}
function open() {
  render(
    <I18nProvider>
      <AuthGate>
        <Secret />
      </AuthGate>
    </I18nProvider>,
  );
}
async function submit() {
  const button = await screen.findByRole("button", { name: "כניסה" });
  fireEvent.change(screen.getByLabelText("שם משתמש"), { target: { value: "admin" } });
  fireEvent.change(screen.getByLabelText("סיסמה"), { target: { value: "pw-123456" } });
  fireEvent.click(button);
}

describe("AuthGate", () => {
  it("hides the app until sign in, then passes on the role", async () => {
    open();
    await submit();
    expect(await screen.findByText("secret app admin")).toBeInTheDocument();
    const body = JSON.parse(String(fetchMock.mock.lastCall?.[1]?.body));
    expect(body).toEqual({ name: "admin", password: "pw-123456" });
  });

  it("is in Hebrew and right to left, also when the app is in English", async () => {
    open();
    expect(await screen.findByRole("main")).toHaveAttribute("dir", "rtl");
  });

  it.each([
    [401, /שגויים/],
    [422, /שגויים/],
    [429, /יותר מדי/],
    [500, /נכשלה/],
  ])("explains a %i and clears the password", async (status, text) => {
    sessionReply = () => json({}, status);
    open();
    await submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.getByLabelText("סיסמה")).toHaveValue("");
    expect(screen.queryByText(/secret app/)).toBeNull();
  });

  it("opens the app without login when the api has it off", async () => {
    me = () => json({ detail: "login_off" }, 404);
    open();
    expect(await screen.findByText("secret app no login")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
  });

  it("does not open the app when the server can't be reached, and retries", async () => {
    me = () => json({}, 502);
    open();
    const retry = await screen.findByRole("button", { name: "Try again" });
    expect(screen.queryByText(/secret app/)).toBeNull();
    me = () => json(admin);
    fireEvent.click(retry);
    expect(await screen.findByText("secret app admin")).toBeInTheDocument();
  });

  it("restores a session and signs out", async () => {
    me = () => json(admin);
    open();
    expect(await screen.findByText("secret app admin")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("button", { name: "כניסה" })).toBeInTheDocument();
    expect(screen.queryByText(/secret app/)).toBeNull();
  });
});
