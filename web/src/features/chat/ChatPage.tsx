import { Bot, FlaskConical, MessageSquarePlus, ShieldCheck } from 'lucide-react';
import { useMemo } from 'react';
import { toast } from 'sonner';
import { Button, EmptyState, Tag } from '../../components/ui';
import { useI18n } from '../../i18n';
import { createMockBackend, SUGGESTIONS } from './backend';
import type { ChatBackend } from './backend';
import { Composer } from './Composer';
import { MessageList } from './MessageList';
import { useChat } from './useChat';
import './chat.css';

export function ChatPage({ backend: injected }: { backend?: ChatBackend }) {
  const { t } = useI18n();
  const backend = useMemo(() => injected ?? createMockBackend(), [injected]);
  const chat = useChat(backend);

  const handlers = useMemo(
    () => ({
      approve: async (id: string) => {
        const device = chat.actions[id]?.device.name ?? '';
        const outcome = await chat.approve(id);
        if (outcome === 'applied') toast.success(t('toast.applied', { device }));
        if (outcome === 'failed') toast.error(t('action.status.failed'));
      },
      cancel: (id: string) => {
        chat.cancel(id);
        toast(t('toast.cancelled'));
      },
      rollback: async (id: string) => {
        const device = chat.actions[id]?.device.name ?? '';
        await chat.rollback(id);
        toast(t('toast.rolledBack', { device }));
      },
    }),
    [chat, t],
  );

  return (
    <div className="chat">
      <header className="chat__header">
        <span className="chat__avatar" aria-hidden="true">
          <Bot size={20} />
        </span>
        <div className="chat__heading">
          <h2>{t('chat.title')}</h2>
          <p>
            <ShieldCheck size={14} aria-hidden="true" />
            {t('chat.subtitle')}
          </p>
        </div>
        <Tag muted>
          <FlaskConical size={12} aria-hidden="true" />
          {t('chat.mockBanner')}
        </Tag>
        <Button variant="ghost" onClick={chat.reset} disabled={chat.messages.length === 0}>
          <MessageSquarePlus size={16} aria-hidden="true" />
          {t('chat.newChat')}
        </Button>
      </header>

      {chat.messages.length === 0 ? (
        <div className="chat__empty">
          <EmptyState icon={<Bot size={28} />} title={t('chat.emptyTitle')} body={t('chat.emptyBody')}>
            <ul className="chat__suggestions">
              {SUGGESTIONS.map((s) => (
                <li key={s}>
                  <button type="button" onClick={() => chat.send(s)}>
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          </EmptyState>
        </div>
      ) : (
        <MessageList messages={chat.messages} actions={chat.actions} handlers={handlers} />
      )}

      <Composer busy={chat.busy} onSend={chat.send} onStop={chat.stop} />
    </div>
  );
}
