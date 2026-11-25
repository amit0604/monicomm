import { fireEvent, render, screen } from "@testing-library/react";
import { I18nProvider } from "../../i18n";
import AuthGate from "./AuthGate";

const password = vi.fn();
const google = vi.fn();
vi.mock("./firebase", () => ({ createSignIn: () => ({ password, google }) }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const config = { api_key: "k", auth_domain: "d", project_id: "p", admin_login: "admin@x.local" };
const admin = { name: "Admin", role: "admin" };
let signedIn = false;
let sessionReply = () => json(admin);

const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url.endsWith("/config")) return json(config);
  if (url.endsWith("/me")) return signedIn ? json(admin) : json({}, 401);
  if (init?.method === "DELETE") return new Response(null, { status: 204 });
  return sessionReply();
});

beforeEach(() => {
  localStorage.setItem("lang", "en");
  signedIn = false;
  sessionReply = () => json(admin);
  password.mockReset().mockResolvedValue("id-token");
  google.mockReset().mockResolvedValue("id-token");
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function open() {
  render(
    <I18nProvider>
      <AuthGate>
        <p>secret app</p>
      </AuthGate>
    </I18nProvider>,
  );
}
async function submit(login: string) {
  const button = await screen.findByRole("button", { name: "כניסה" });
  await vi.waitFor(() => expect(button).toBeEnabled());
  fireEvent.change(screen.getByLabelText("שם משתמש או אימייל"), { target: { value: login } });
  fireEvent.change(screen.getByLabelText("סיסמה"), { target: { value: "pw-123456" } });
  fireEvent.click(button);
}

describe("AuthGate", () => {
  it("hides the app until sign in, and maps the admin username to its email", async () => {
    open();
    await submit("admin");
    expect(await screen.findByText("secret app")).toBeInTheDocument();
    expect(password).toHaveBeenCalledWith("admin@x.local", "pw-123456");
  });

  it("is in Hebrew and right to left, also when the app is in English", async () => {
    open();
    expect(await screen.findByRole("main")).toHaveAttribute("dir", "rtl");
    expect(screen.queryByRole("button", { name: "English" })).toBeNull();
  });

  it("signs in with Google", async () => {
    open();
    const button = await screen.findByRole("button", { name: "כניסה עם Google" });
    await vi.waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    expect(await screen.findByText("secret app")).toBeInTheDocument();
  });

  it.each([
    ["wrong password", { code: "auth/invalid-credential" }, /שגויים/],
    ["unknown failure", new Error("x"), /נכשלה/],
  ])("explains %s", async (_name, error, text) => {
    password.mockRejectedValue(error);
    open();
    await submit("a@b.co");
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.queryByText("secret app")).toBeNull();
  });

  it("refuses a Google account that is not on the list", async () => {
    sessionReply = () => json({ detail: "not_allowed" }, 403);
    open();
    await submit("a@b.co");
    expect(await screen.findByRole("alert")).toHaveTextContent("אין גישה");
  });

  it("restores a session and signs out", async () => {
    signedIn = true;
    open();
    expect(await screen.findByText("secret app")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("button", { name: "כניסה" })).toBeInTheDocument();
    expect(screen.queryByText("secret app")).toBeNull();
  });
});
