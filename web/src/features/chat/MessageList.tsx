import { ArrowDown } from 'lucide-react';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import { MessageBubble } from './MessageBubble';
import type { ActionHandlers } from './MessageBubble';
import type { ChatMessage, ProposedAction } from './types';

const STICK_THRESHOLD = 80;

/** WhatsApp-style scroll: follows new content while you're at the bottom, and leaves you alone when you scroll up. */
export function MessageList({
  messages,
  actions,
  handlers,
}: {
  messages: ChatMessage[];
  actions: Record<string, ProposedAction>;
  handlers: ActionHandlers;
}) {
  const { t } = useI18n();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);

  const scrollToBottom = (behavior: ScrollBehavior = 'auto') => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior });
  };

  useLayoutEffect(() => {
    if (atBottom) scrollToBottom();
  }, [messages, actions, atBottom]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < STICK_THRESHOLD);
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <div className="msg-list">
      <div className="msg-list__scroll" ref={scrollRef} role="log" aria-live="polite" aria-relevant="additions">
        <div className="msg-list__day">
          <span>{t('chat.today')}</span>
        </div>
        <ol className="msg-list__items">
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} actions={actions} handlers={handlers} />
          ))}
        </ol>
      </div>
      {!atBottom && (
        <button type="button" className="msg-list__jump" onClick={() => scrollToBottom('smooth')} aria-label={t('chat.jumpToLatest')}>
          <ArrowDown size={18} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
