import { CheckCircle2, LoaderCircle, Wrench, XCircle } from 'lucide-react';
import { Tag } from '../../../components/ui';
import { useI18n } from '../../../i18n';
import type { Part } from '../types';

type ToolPart = Extract<Part, { type: 'tool_call' }>;

/** Every tool call is visible in the conversation (OpenCode-style), so the technician sees what the AI read. */
export function ToolCall({ part }: { part: ToolPart }) {
  const { t } = useI18n();
  const args = Object.entries(part.args)
    .map(([k, v]) => `${k}=${v}`)
    .join(' ');

  return (
    <div className={`tool-call tool-call--${part.status}`}>
      <span className="tool-call__icon" aria-hidden="true">
        {part.status === 'running' ? (
          <LoaderCircle size={14} className="spin" />
        ) : part.status === 'done' ? (
          <CheckCircle2 size={14} />
        ) : (
          <XCircle size={14} />
        )}
      </span>
      <Wrench size={14} aria-hidden="true" className="tool-call__wrench" />
      <code className="tool-call__name">{part.tool}</code>
      <code className="tool-call__args">{args}</code>
      {part.summary && <span className="tool-call__summary">→ {part.summary}</span>}
      <span className="tool-call__meta">
        <Tag muted>{t('tool.readOnly')}</Tag>
        <span className="visually-hidden">{part.status === 'running' ? t('tool.running') : t('tool.done')}</span>
        {part.durationMs !== undefined && <span className="num">{part.durationMs} ms</span>}
      </span>
    </div>
  );
}
