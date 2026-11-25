import { fireEvent, render, screen } from "@testing-library/react";
import { I18nProvider } from "../../i18n";
import { AdminEmails } from "./AdminEmails";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const fetchMock = vi.fn();

beforeEach(() => {
  localStorage.setItem("lang", "en");
  fetchMock.mockReset();
  fetchMock.mockResolvedValueOnce(json({ env: ["env@x.co"], saved: ["a@x.co"] }));
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("confirm", () => true);
});
afterEach(() => vi.unstubAllGlobals());

const open = () =>
  render(
    <I18nProvider>
      <AdminEmails />
    </I18nProvider>,
  );
const sent = () => JSON.parse(String(fetchMock.mock.lastCall?.[1]?.body));
async function add(email: string) {
  fireEvent.change(await screen.findByLabelText("Admin email"), { target: { value: email } });
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
}

describe("AdminEmails", () => {
  it("adds an email to the saved ones and empties the field", async () => {
    fetchMock.mockResolvedValueOnce(json({ env: ["env@x.co"], saved: ["a@x.co", "b@x.co"] }));
    open();
    await add("b@x.co");
    expect(await screen.findByText("b@x.co")).toBeInTheDocument();
    expect(sent()).toEqual({ emails: ["a@x.co", "b@x.co"] });
    expect(screen.getByLabelText("Admin email")).toHaveValue("");
  });

  it("removes a saved email, and offers no removal for one from .env", async () => {
    fetchMock.mockResolvedValueOnce(json({ env: ["env@x.co"], saved: [] }));
    open();
    expect(await screen.findAllByRole("button", { name: /^Remove/ })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Remove a@x.co" }));
    await vi.waitFor(() => expect(screen.queryByText("a@x.co")).toBeNull());
    expect(sent()).toEqual({ emails: [] });
  });

  it("explains a refused address and keeps what was typed", async () => {
    fetchMock.mockResolvedValueOnce(json({}, 422));
    open();
    await add("b@x.co");
    expect(await screen.findByRole("alert")).toHaveTextContent("not valid");
    expect(screen.getByLabelText("Admin email")).toHaveValue("b@x.co");
  });

  it("shows nothing to someone without access", async () => {
    fetchMock.mockReset().mockResolvedValueOnce(json({}, 401));
    const { container } = open();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
