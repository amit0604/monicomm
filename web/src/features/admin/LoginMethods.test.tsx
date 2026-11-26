import { fireEvent, render, screen, within } from "@testing-library/react";
import { I18nProvider } from "../../i18n";
import { LoginMethods } from "./LoginMethods";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const LDAP = {
  url: "ldaps://dc01.corp.example:636",
  start_tls: false,
  ca_file: "",
  bind_dn: "cn=svc,dc=corp,dc=example",
  base_dn: "dc=corp,dc=example",
  user_filter: "(sAMAccountName={username})",
  admin_group: "",
  technician_group: "",
  default_role: "viewer",
  enabled: true,
  saved: false,
  secret_source: "env",
};
const SSO = {
  issuer: "",
  client_id: "",
  scopes: "openid profile email",
  groups_claim: "groups",
  admin_group: "",
  technician_group: "",
  default_role: "viewer",
  label: "SSO",
  redirect_url: "",
  ca_file: "",
  enabled: false,
  saved: false,
  secret_source: "none",
  callback_url: "https://monicomm.corp.internal/api/v1/auth/sso/callback",
};

let testReply: () => Response;
const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url.endsWith("/ldap/test")) return testReply();
  if (url.endsWith("/ldap")) return json(init?.method === "PUT" ? { ...LDAP, saved: true } : LDAP);
  if (url.endsWith("/sso")) return json(SSO);
  return json({}, 404);
});

beforeEach(() => {
  localStorage.setItem("lang", "en");
  testReply = () => json({ ok: true, error: null, user: null });
  fetchMock.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

async function ldapPanel() {
  render(
    <I18nProvider>
      <LoginMethods />
    </I18nProvider>,
  );
  return within(await screen.findByRole("form", { name: "LDAP / Active Directory" }));
}

const lastBody = () => JSON.parse(String(fetchMock.mock.lastCall?.[1]?.body));

describe("Login methods on the Admin page", () => {
  it("shows LDAP and SSO with their state and the SSO callback to register", async () => {
    const ldap = await ldapPanel();
    expect(ldap.getByLabelText("Server address")).toHaveValue(LDAP.url);
    expect(screen.getByText("On")).toBeInTheDocument();
    const sso = within(
      await screen.findByRole("form", { name: "Single sign-on (OpenID Connect)" }),
    );
    expect(sso.getByText(SSO.callback_url)).toBeInTheDocument();
  });

  it("never shows the secret, and keeps it when left empty", async () => {
    const ldap = await ldapPanel();
    const secret = ldap.getByLabelText("Service account password");
    expect(secret).toHaveValue("");
    expect(secret).toHaveAttribute("placeholder", "Leave empty to keep the current one");
    fireEvent.click(ldap.getByRole("button", { name: "Save" }));
    expect(await ldap.findByRole("status")).toHaveTextContent("Saved");
    expect(lastBody().bind_password).toBeNull();
  });

  it("tests the connection with what is on screen, and looks up a user", async () => {
    testReply = () =>
      json({
        ok: true,
        error: null,
        user: { dn: "cn=bob,dc=corp,dc=example", role: "technician" },
      });
    const ldap = await ldapPanel();
    fireEvent.change(ldap.getByLabelText("Search base DN"), { target: { value: "dc=lab" } });
    fireEvent.change(ldap.getByLabelText("User to look up in the test (optional)"), {
      target: { value: "bob" },
    });
    fireEvent.click(ldap.getByRole("button", { name: "Test connection" }));
    expect(await ldap.findByRole("status")).toHaveTextContent(
      "Connected. Found cn=bob,dc=corp,dc=example, role: technician.",
    );
    expect(lastBody()).toMatchObject({ base_dn: "dc=lab", username: "bob" });
  });

  it("explains a failed test", async () => {
    testReply = () => json({ ok: false, error: "bind_failed", user: null });
    const ldap = await ldapPanel();
    fireEvent.click(ldap.getByRole("button", { name: "Test connection" }));
    expect(await ldap.findByRole("alert")).toHaveTextContent("The service account was refused");
  });
});
