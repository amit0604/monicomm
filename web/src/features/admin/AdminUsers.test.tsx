import { fireEvent, render, screen } from "@testing-library/react";
import { I18nProvider } from "../../i18n";
import { AdminUsers } from "./AdminUsers";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const admin = { name: "admin", role: "admin" };
const tech = { name: "tech@x.co", role: "technician" };
const fetchMock = vi.fn();

beforeEach(() => {
  localStorage.setItem("lang", "en");
  fetchMock.mockReset();
  fetchMock.mockResolvedValueOnce(json([admin, tech]));
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("confirm", () => true);
});
afterEach(() => vi.unstubAllGlobals());

const open = () =>
  render(
    <I18nProvider>
      <AdminUsers />
    </I18nProvider>,
  );
const last = () => fetchMock.mock.lastCall as [string, RequestInit];
const type = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } });

async function add() {
  await screen.findByText("tech@x.co");
  type("Username", "new");
  type("Password (at least 8 characters)", "pw-12345678");
  fireEvent.click(screen.getByRole("button", { name: "Add user" }));
}

describe("AdminUsers", () => {
  it("adds a user and empties the form", async () => {
    fetchMock.mockResolvedValueOnce(json([admin, tech, { name: "new", role: "technician" }]));
    open();
    await add();
    expect(await screen.findByText("new")).toBeInTheDocument();
    expect(JSON.parse(String(last()[1].body))).toEqual({
      name: "new",
      role: "technician",
      password: "pw-12345678",
    });
    expect(screen.getByLabelText("Username")).toHaveValue("");
  });

  it("replaces a password", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    open();
    fireEvent.click(await screen.findByRole("button", { name: "New password for tech@x.co" }));
    type("Password (at least 8 characters)", "pw-12345678");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Password changed");
    expect(last()[0]).toBe("/api/v1/admin/users/tech%40x.co/password");
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
  });

  it("removes a user", async () => {
    fetchMock.mockResolvedValueOnce(json([admin]));
    open();
    fireEvent.click(await screen.findByRole("button", { name: "Remove tech@x.co" }));
    await vi.waitFor(() => expect(screen.queryByText("tech@x.co")).toBeNull());
    expect(last()[1].method).toBe("DELETE");
  });

  it.each([
    [409, { detail: "exists" }, /already exists/],
    [422, {}, /not valid/],
    [500, {}, /failed/],
  ])("explains a %i and keeps what was typed", async (status, body, text) => {
    fetchMock.mockResolvedValueOnce(json(body, status));
    open();
    await add();
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.getByLabelText("Username")).toHaveValue("new");
  });

  it("explains that the last admin stays", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "last_admin" }, 409));
    open();
    fireEvent.click(await screen.findByRole("button", { name: "Remove admin" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("last admin");
  });

  it("shows nothing to someone without access", async () => {
    fetchMock.mockReset().mockResolvedValueOnce(json({}, 403));
    const { container } = open();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
