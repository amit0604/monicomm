import { en } from "../../i18n/en";
import type { MessageKey } from "../../i18n/en";
import { createHttpBackend } from "./backend";
import type { AssistantEvent } from "./types";

const t = (key: MessageKey) => en[key];
const reply = (text: string, source = "demo") => ({
  source,
  reply: text,
  model: "qwen2.5:7b",
  context: {
    collected_at: "2026-11-25T10:00:00Z",
    included: { devices: 22, alerts: 3, events: 40 },
    totals: { devices: 22, alerts: 3, events: 90 },
  },
});

function fakeFetch(...responses: [number, unknown][]) {
  const calls: unknown[] = [];
  const fn = vi.fn(async (_url: unknown, init?: RequestInit) => {
    calls.push(JSON.parse(String(init?.body)));
    const [status, body] = responses.shift()!;
    return new Response(JSON.stringify(body), { status });
  });
  return { fn: fn as unknown as typeof fetch, calls };
}

async function collect(gen: AsyncGenerator<AssistantEvent>) {
  const out: AssistantEvent[] = [];
  for await (const e of gen) out.push(e);
  return out;
}

const turn = { turns: [{ intent: "NETWORK_INFORMATION" as const, concepts: [], entries: [] }] };

describe("createHttpBackend", () => {
  it("returns the model reply with demo-labeled sources", async () => {
    const { fn } = fakeFetch([200, reply("all good")]);
    const events = await collect(
      createHttpBackend(t, fn).ask("status?", new AbortController().signal),
    );
    expect(events).toContainEqual({ type: "text_delta", text: "all good" });
    const sources = events.find((e) => e.type === "sources");
    expect(sources?.type === "sources" && sources.sources.map((s) => [s.label, s.mock])).toEqual([
      ["22/22 devices", true],
      ["3/3 alerts", true],
      ["40/90 events", true],
    ]);
  });

  it("sends history on a follow-up and drops it after New chat", async () => {
    const { fn, calls } = fakeFetch(
      [200, reply("one", "live")],
      [200, reply("two")],
      [200, reply("x")],
    );
    const backend = createHttpBackend(t, fn);
    const signal = new AbortController().signal;
    await collect(backend.ask("q1", signal));
    await collect(backend.ask("q2", signal, turn));
    await collect(backend.ask("q3", signal, { turns: [] }));
    expect(calls).toEqual([
      { messages: [{ role: "user", content: "q1" }] },
      {
        messages: [
          { role: "user", content: "q1" },
          { role: "assistant", content: "one" },
          { role: "user", content: "q2" },
        ],
      },
      { messages: [{ role: "user", content: "q3" }] },
    ]);
  });

  it("explains API errors in words", async () => {
    const { fn } = fakeFetch([503, { detail: "llm_unavailable" }], [500, { detail: "boom" }]);
    const backend = createHttpBackend(t, fn);
    const signal = new AbortController().signal;
    expect(await collect(backend.ask("a", signal))).toEqual([
      { type: "text_delta", text: en["chat.error.llm_unavailable"] },
    ]);
    expect(await collect(backend.ask("b", signal))).toEqual([
      { type: "text_delta", text: en["chat.error.failed"] },
    ]);
  });

  it("never applies changes: Chat AI is read-only on the API", async () => {
    const backend = createHttpBackend(t, fakeFetch().fn);
    await expect(backend.rollback({} as never)).rejects.toThrow();
    await expect(backend.applyApproved({} as never, "id", [])).rejects.toThrow();
  });
});
