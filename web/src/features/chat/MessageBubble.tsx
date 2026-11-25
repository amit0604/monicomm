import { Bot, ServerCog } from 'lucide-react';
import { Tag } from '../../components/ui';
import { useI18n } from '../../i18n';
import { ActionCard } from './parts/ActionCard';
import { CodeBlock } from './parts/CodeBlock';
import { DataTable } from './parts/DataTable';
import { RichText } from './parts/RichText';
import { Sources } from './parts/Sources';
import { ToolCall } from './parts/ToolCall';
import type { ChatMessage, ProposedAction } from './types';

export interface ActionHandlers {
  approve: (id: string) => void;
  cancel: (id: string) => void;
  rollback: (id: string) => void;
}

const timeFormat = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' });

export function MessageBubble({
  message,
  actions,
  handlers,
}: {
  message: ChatMessage;
  actions: Record<string, ProposedAction>;
  handlers: ActionHandlers;
}) {
  const { t } = useI18n();
  const isUser = message.role === 'user';
  const time = timeFormat.format(message.createdAt);

  return (
    <li className={`msg msg--${message.role}`}>
      {!isUser && (
        <span className="msg__avatar" aria-hidden="true">
          {message.role === 'assistant' ? <Bot size={18} /> : <ServerCog size={18} />}
        </span>
      )}
      <div className="msg__bubble">
        {!isUser && (
          <div className="msg__author">
            <span>{message.role === 'assistant' ? t('chat.title') : t('chat.configurator')}</span>
            {message.role === 'assistant' && <Tag>{t('chat.aiTag')}</Tag>}
          </div>
        )}

        <div className="msg__body">
          {message.parts.map((part, i) => {
            switch (part.type) {
              case 'text':
                return <RichText key={i} text={part.text} />;
              case 'tool_call':
                return <ToolCall key={part.id} part={part} />;
              case 'table':
                return <DataTable key={i} title={part.title} columns={part.columns} rows={part.rows} />;
              case 'code':
                return <CodeBlock key={i} title={part.title} language={part.language} content={part.content} />;
              case 'action': {
                const action = actions[part.actionId];
                return action ? (
                  <ActionCard
                    key={part.actionId}
                    action={action}
                    onApprove={() => handlers.approve(action.id)}
                    onCancel={() => handlers.cancel(action.id)}
                    onRollback={() => handlers.rollback(action.id)}
                  />
                ) : null;
              }
            }
          })}
          {message.streaming && message.parts.length === 0 && (
            <span className="typing" aria-label={t('chat.typing')}>
              <span />
              <span />
              <span />
            </span>
          )}
        </div>

        {message.sources && message.sources.length > 0 && <Sources sources={message.sources} />}

        <time className="msg__time num" dateTime={new Date(message.createdAt).toISOString()}>
          {time}
        </time>
      </div>
    </li>
  );
}
