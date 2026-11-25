// The one seam between the ChatIAF UI and its backend. Today it's the in-browser mock;
// when api/app/modules/chat lands, add an HTTP implementation with the same interface and switch here.
import * as assistant from './mock/assistant';
import * as configurator from './mock/configurator';
import type { ConversationContext } from './mock/intent';
import type { ActionResult, AssistantEvent, ProposedAction } from './types';

export type { ConversationContext };

export interface ChatBackend {
  /**
   * Streams one assistant reply. Read-only: the reply can propose actions but never apply them.
   * `context` summarizes earlier replies in this chat (empty after "New chat") so follow-ups can refer back.
   */
  ask(question: string, signal: AbortSignal, context?: ConversationContext): AsyncGenerator<AssistantEvent>;
  /** Called only by the approval UI, after a human approved. */
  applyApproved(action: ProposedAction, approvalId: string, approvers: string[]): Promise<ActionResult>;
  rollback(action: ProposedAction): Promise<string>;
}

export function createMockBackend(pace = 1): ChatBackend {
  return {
    ask: (question, signal, context) => assistant.respond(question, { signal, pace: 18 * pace, context }),
    applyApproved: (action, approvalId, approvers) => configurator.apply({ action, approvalId, approvers }, pace),
    rollback: (action) => configurator.rollback(action, pace),
  };
}

export const SUGGESTIONS = assistant.SUGGESTIONS;
