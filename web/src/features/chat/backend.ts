// The one seam between the ChatIAF UI and its backend: the in-browser mock (prototype, with the
// approval flow) or the API (POST /api/v1/chat, answers from current Monicomm data, read-only).
// Pick one at build time with VITE_CHAT_BACKEND=api|mock (default mock).
import type { MessageKey } from "../../i18n/en";
import * as assistant from "./mock/assistant";
import * as configurator from "./mock/configurator";
import type { ConversationContext } from "./mock/intent";
import type { ActionResult, AssistantEvent, ProposedAction, Source } from "./types";

export type { ConversationContext };

export interface ChatBackend {
  /**
   * Streams one assistant reply. Read-only: the reply can propose actions but never apply them.
   * `context` summarizes earlier replies in this chat (empty after "New chat") so follow-ups can refer back.
   */
  ask(
    question: string,
    signal: AbortSignal,
    context?: ConversationContext,
  ): AsyncGenerator<AssistantEvent>;
  /** Called only by the approval UI, after a human approved. */
  applyApproved(
    action: ProposedAction,
    approvalId: string,
    approvers: string[],
  ): Promise<ActionResult>;
  rollback(action: ProposedAction): Promise<string>;
}

export function createMockBackend(pace = 1): ChatBackend {
  return {
    ask: (question, signal, context) =>
      assistant.respond(question, { signal, pace: 18 * pace, context }),
    applyApproved: (action, approvalId, approvers) =>
      configurator.apply({ action, approvalId, approvers }, pace),
    rollback: (action) => configurator.rollback(action, pace),
  };
}

export const SUGGESTIONS = assistant.SUGGESTIONS;

// Mirrors api/app/modules/chat/service.py (ChatReply).
interface Counts {
  devices: number;
  alerts: number;
  events: number;
}
interface ApiReply {
  source: "demo" | "live";
  reply: string;
  model: string;
  context: { collected_at: string; included: Counts; totals: Counts };
}

const API_ERRORS = ["no_data_source", "not_allowed", "llm_unavailable"] as const;
const MAX_HISTORY = 20; // the server keeps no more than this

type Translate = (key: MessageKey) => string;

/** The live backend. It has no tools and no approval flow: Chat AI stays read-only. */
export function createHttpBackend(t: Translate, fetcher: typeof fetch = fetch): ChatBackend {
  let history: { role: "user" | "assistant"; content: string }[] = [];
  const unavailable = () => Promise.reject(new Error("Changes are not available on the live API"));

  return {
    async *ask(question, signal, context) {
      if (!context || context.turns.length === 0) history = []; // "New chat"
      const messages = [
        ...history.slice(-MAX_HISTORY),
        { role: "user" as const, content: question },
      ];
      let res: Response;
      let body: Partial<ApiReply> & { detail?: string };
      try {
        res = await fetcher("/api/v1/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ messages }),
          signal,
        });
        body = await res.json();
      } catch (e) {
        if (signal.aborted) throw e;
        yield { type: "text_delta", text: t("chat.error.failed") };
        return;
      }
      if (!res.ok || typeof body.reply !== "string" || !body.context) {
        const code = API_ERRORS.find((c) => c === body.detail) ?? "failed";
        yield { type: "text_delta", text: t(`chat.error.${code}`) };
        return;
      }
      history = [...messages, { role: "assistant", content: body.reply }];
      yield {
        type: "meta",
        meta: {
          intent: "NETWORK_INFORMATION",
          concepts: [],
          entries: [],
          confidence: "medium",
          reason: `${body.model} (${body.source})`,
          engine: "model",
        },
      };
      yield { type: "text_delta", text: body.reply };
      const { included, totals, collected_at } = body.context;
      const source = (id: keyof Counts, kind: Source["kind"]): Source => ({
        id,
        kind,
        label: `${included[id]}/${totals[id]} ${id}`,
        detail: collected_at,
        mock: body.source === "demo",
      });
      const sources = [
        source("devices", "inventory"),
        source("alerts", "alert"),
        source("events", "log"),
      ];
      yield { type: "sources", sources };
    },
    applyApproved: unavailable,
    rollback: unavailable,
  };
}

export function createBackend(t: Translate): ChatBackend {
  return import.meta.env.VITE_CHAT_BACKEND === "api" ? createHttpBackend(t) : createMockBackend();
}
