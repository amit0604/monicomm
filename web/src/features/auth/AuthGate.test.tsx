import { fireEvent, render, screen } from "@testing-library/react";
import { Account } from "../../components/layout/Account";
import { I18nProvider } from "../../i18n";
import { AuthGate } from "./AuthGate";
import { useSession } from "./session";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const admin = { name: "admin", role: "admin" };
let me: () => Response;
let sessionReply: () => Response;
let methods: () => Response;

const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url.endsWith("/me")) return me();
  if (url.endsWith("/methods")) return methods();
  if (init?.method === "DELETE") return new Response(null, { status: 204 });
  return sessionReply();
});

beforeEach(() => {
  localStorage.setItem("lang", "en");
  me = () => json({}, 401);
  sessionReply = () => json(admin);
  methods = () => json({ local: true, ldap: false, sso: null });
  fetchMock.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function Secret() {
  return (
    <>
      <p>secret app {useSession()?.role ?? "no login"}</p>
      <Account collapsed={false} />
    </>
  );
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
    [403, /אין גישה/],
    [503, /שרת הספרייה/],
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

  it("offers SSO when it is on, as a link to the identity provider", async () => {
    methods = () => json({ local: true, ldap: true, sso: { label: "Corp SSO" } });
    open();
    const link = await screen.findByRole("link", { name: "כניסה עם Corp SSO" });
    expect(link).toHaveAttribute("href", "/api/v1/auth/sso/start");
  });

  it("explains an SSO sign in that came back with an error, once", async () => {
    window.history.replaceState(null, "", "/?sso=not_allowed");
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent(/אין גישה/);
    expect(window.location.search).toBe("");
  });

  it("shows the account in the app, with where it signs in from", async () => {
    me = () =>
      json({
        name: "dana",
        role: "technician",
        display_name: "Dana Cohen",
        email: "dana@corp.example",
        source: "sso",
      });
    open();
    const account = await screen.findByRole("region", { name: "Account" });
    expect(account).toHaveTextContent("Dana Cohen");
    expect(account).toHaveTextContent("dana@corp.example");
    expect(account).toHaveTextContent("Technician · SSO");
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
