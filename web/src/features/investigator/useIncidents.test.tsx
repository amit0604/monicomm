import { render, waitFor } from "@testing-library/react";
import { toast } from "sonner";
import { useCriticalIncidentToasts } from "./useIncidents";
import { stubFetch, SUMMARY } from "./testData";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(toast.error).mockClear();
});

function Probe({ onOpen }: { onOpen: (id: string) => void }) {
  useCriticalIncidentToasts(onOpen, 10);
  return null;
}

describe("useCriticalIncidentToasts", () => {
  it("toasts once per new critical id, never for incidents present on first load", async () => {
    const existing = { ...SUMMARY, id: "000000000000" };
    const fresh = { ...SUMMARY, id: "111111111111", title: "Link down: new" };
    const warning = { ...SUMMARY, id: "222222222222", severity: "warning" as const };
    let calls = 0;
    const fetchMock = stubFetch({
      "GET /api/v1/investigator/incidents": () => [
        200,
        calls++ === 0 ? [existing] : [fresh, warning, existing],
      ],
    });
    const onOpen = vi.fn();
    render(<Probe onOpen={onOpen} />);

    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    // Several more polls return the same incidents: still exactly one toast.
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(4));
    expect(toast.error).toHaveBeenCalledTimes(1);

    const [title, opts] = vi.mocked(toast.error).mock.calls[0];
    expect(title).toBe("Link down: new");
    expect(opts?.id).toBe(fresh.id);
    (opts?.action as unknown as { onClick: () => void }).onClick();
    expect(onOpen).toHaveBeenCalledWith(fresh.id);
  });
});
