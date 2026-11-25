import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import type { ChatBackend, ConversationContext } from './backend';
import type { ActionResult, AssistantEvent, ChatMessage, Part, ProposedAction } from './types';

export const CURRENT_USER = 'technician';
const DEMO_SECOND_APPROVER = 'technician-2';

interface State {
  messages: ChatMessage[];
  actions: Record<string, ProposedAction>;
  busy: boolean;
}

type Action =
  | { type: 'user_message'; message: ChatMessage }
  | { type: 'assistant_start'; message: ChatMessage }
  | { type: 'assistant_event'; messageId: string; event: AssistantEvent }
  | { type: 'assistant_end'; messageId: string }
  | { type: 'append_message'; message: ChatMessage }
  | { type: 'update_action'; id: string; patch: Partial<ProposedAction> }
  | { type: 'reset' };

const initial: State = { messages: [], actions: {}, busy: false };

let seq = 0;
const nextId = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${++seq}`;

function applyEvent(message: ChatMessage, event: AssistantEvent): ChatMessage {
  const parts = [...message.parts];
  const last = parts[parts.length - 1];
  switch (event.type) {
    case 'text_delta':
      if (last?.type === 'text') parts[parts.length - 1] = { ...last, text: last.text + event.text };
      else parts.push({ type: 'text', text: event.text.trimStart() });
      break;
    case 'tool_start':
      parts.push({ type: 'tool_call', id: event.id, tool: event.tool, args: event.args, status: 'running' });
      break;
    case 'tool_end': {
      const i = parts.findIndex((p) => p.type === 'tool_call' && p.id === event.id);
      if (i >= 0) {
        const p = parts[i] as Extract<Part, { type: 'tool_call' }>;
        parts[i] = { ...p, status: 'done', summary: event.summary, durationMs: event.durationMs };
      }
      break;
    }
    case 'table':
      parts.push({ type: 'table', title: event.title, columns: event.columns, rows: event.rows });
      break;
    case 'code':
      parts.push({ type: 'code', title: event.title, language: event.language, content: event.content });
      break;
    case 'proposal':
      parts.push({ type: 'action', actionId: event.action.id });
      break;
    case 'sources':
      return { ...message, parts, sources: [...(message.sources ?? []), ...event.sources] };
    case 'meta':
      return { ...message, parts, meta: event.meta };
  }
  return { ...message, parts };
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'user_message':
      return { ...state, messages: [...state.messages, action.message] };
    case 'assistant_start':
      return { ...state, busy: true, messages: [...state.messages, action.message] };
    case 'assistant_event': {
      const actions =
        action.event.type === 'proposal'
          ? { ...state.actions, [action.event.action.id]: action.event.action }
          : state.actions;
      return {
        ...state,
        actions,
        messages: state.messages.map((m) => (m.id === action.messageId ? applyEvent(m, action.event) : m)),
      };
    }
    case 'assistant_end':
      return {
        ...state,
        busy: false,
        messages: state.messages.map((m) => {
          if (m.id !== action.messageId) return m;
          // Any tool call still running when the reply stops (for example, Stop was pressed) is marked failed.
          const parts = m.parts.map((p) => (p.type === 'tool_call' && p.status === 'running' ? { ...p, status: 'error' as const } : p));
          return { ...m, parts, streaming: false };
        }),
      };
    case 'append_message':
      return { ...state, messages: [...state.messages, action.message] };
    case 'update_action': {
      const current = state.actions[action.id];
      if (!current) return state;
      return { ...state, actions: { ...state.actions, [action.id]: { ...current, ...action.patch } } };
    }
    case 'reset':
      return initial;
  }
}

function configuratorMessage(text: string, output?: string): ChatMessage {
  const parts: Part[] = [{ type: 'text', text }];
  if (output) parts.push({ type: 'code', language: 'log', title: 'Configurator output', content: output });
  return { id: nextId('cfg'), role: 'configurator', createdAt: Date.now(), parts };
}

/** Conversation context for follow-ups: what each earlier assistant reply in this chat was about. */
export function contextFrom(messages: ChatMessage[]): ConversationContext {
  return {
    turns: messages
      .filter((m) => m.role === 'assistant' && m.meta)
      .slice(-5)
      .map(({ meta }) => ({
        intent: meta!.intent,
        concepts: meta!.concepts,
        entries: meta!.entries,
        scenario: meta!.scenario,
        detailShown: meta!.detailShown,
      })),
  };
}

export function useChat(backend: ChatBackend) {
  const [state, dispatch] = useReducer(reducer, initial);
  const abortRef = useRef<AbortController | null>(null);
  // Read inside send() without making send change on every message.
  const messagesRef = useRef(state.messages);
  useEffect(() => {
    messagesRef.current = state.messages;
  }, [state.messages]);

  const send = useCallback(
    async (text: string) => {
      const question = text.trim();
      if (!question || abortRef.current) return;
      const context = contextFrom(messagesRef.current);

      dispatch({
        type: 'user_message',
        message: { id: nextId('user'), role: 'user', createdAt: Date.now(), parts: [{ type: 'text', text: question }] },
      });
      const messageId = nextId('ai');
      dispatch({ type: 'assistant_start', message: { id: messageId, role: 'assistant', createdAt: Date.now(), parts: [], streaming: true } });

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        for await (const event of backend.ask(question, controller.signal, context)) {
          dispatch({ type: 'assistant_event', messageId, event });
        }
      } catch (err) {
        if (!(err instanceof DOMException && err.name === 'AbortError')) {
          dispatch({ type: 'assistant_event', messageId, event: { type: 'text_delta', text: `\n\nSomething went wrong: ${String(err)}` } });
        }
      } finally {
        abortRef.current = null;
        dispatch({ type: 'assistant_end', messageId });
      }
    },
    [backend],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const runApply = useCallback(
    async (action: ProposedAction, approvers: string[]) => {
      const approvalId = `APR-${Math.floor(100000 + Math.random() * 900000)}`;
      dispatch({ type: 'update_action', id: action.id, patch: { approvals: approvers, approvalId, status: 'applying' } });
      let result: ActionResult;
      try {
        result = await backend.applyApproved(action, approvalId, approvers);
      } catch (err) {
        dispatch({ type: 'update_action', id: action.id, patch: { status: 'failed', result: { checks: [], output: String(err) } } });
        dispatch({ type: 'append_message', message: configuratorMessage(`${action.id} failed on ${action.device.name}.`, String(err)) });
        return 'failed' as const;
      }
      dispatch({ type: 'update_action', id: action.id, patch: { status: 'verifying' } });
      await new Promise((r) => setTimeout(r, 600));
      const ok = result.checks.every((c) => c.ok);
      dispatch({ type: 'update_action', id: action.id, patch: { status: ok ? 'applied' : 'failed', result } });
      dispatch({
        type: 'append_message',
        message: configuratorMessage(
          ok
            ? `✅ Simulated: ${action.id} applied on ${action.device.name}. Health checks passed. No real device was contacted.`
            : `↩️ Simulated: ${action.id} on ${action.device.name} failed its health checks and was rolled back automatically. No real device was contacted.`,
          result.output,
        ),
      });
      return ok ? ('applied' as const) : ('failed' as const);
    },
    [backend],
  );

  const approve = useCallback(
    async (id: string) => {
      const action = state.actions[id];
      if (!action || (action.status !== 'pending' && action.status !== 'awaiting_second')) return null;
      const approvers = action.approvals.includes(CURRENT_USER) ? [...action.approvals, DEMO_SECOND_APPROVER] : [CURRENT_USER];
      if (approvers.length < action.approvalsRequired) {
        dispatch({ type: 'update_action', id, patch: { approvals: approvers, status: 'awaiting_second' } });
        return 'awaiting_second' as const;
      }
      return runApply(action, approvers);
    },
    [runApply, state.actions],
  );

  const cancel = useCallback((id: string) => {
    dispatch({ type: 'update_action', id, patch: { status: 'cancelled' } });
  }, []);

  const rollback = useCallback(
    async (id: string) => {
      const action = state.actions[id];
      if (!action || action.status !== 'applied') return;
      const output = await backend.rollback(action);
      dispatch({ type: 'update_action', id, patch: { status: 'rolled_back' } });
      dispatch({ type: 'append_message', message: configuratorMessage(`↩️ Simulated: ${action.id} rolled back on ${action.device.name}. No real device was contacted.`, output) });
    },
    [backend, state.actions],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    // Clears messages, and with them the conversation context.
    messagesRef.current = [];
    dispatch({ type: 'reset' });
  }, []);

  return useMemo(
    () => ({ ...state, send, stop, approve, cancel, rollback, reset }),
    [state, send, stop, approve, cancel, rollback, reset],
  );
}
