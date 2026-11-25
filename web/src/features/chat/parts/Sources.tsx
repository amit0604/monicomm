import { Bell, BookOpen, FileCode2, HardDrive, LineChart, ScrollText, Table2 } from 'lucide-react';
import { Tag } from '../../../components/ui';
import { useI18n } from '../../../i18n';
import type { Source } from '../types';

const ICONS = {
  device: HardDrive,
  log: ScrollText,
  metric: LineChart,
  config: FileCode2,
  alert: Bell,
  inventory: Table2,
  knowledge: BookOpen,
} as const;

/**
 * Evidence or it didn't happen (PROJECT.md AI rule 4): every AI answer lists what it was based on.
 * In the prototype, network sources point at mock data and are labeled so.
 */
export function Sources({ sources }: { sources: Source[] }) {
  const { t } = useI18n();
  if (sources.length === 0) return null;
  const hasMock = sources.some((s) => s.kind !== 'knowledge');
  return (
    <details className="sources">
      <summary>
        {t('chat.sources')} <span className="num">({sources.length})</span>
      </summary>
      {hasMock && <p className="sources__note">{t('chat.sourcesMockNote')}</p>}
      <ul>
        {sources.map((s) => {
          const Icon = ICONS[s.kind];
          return (
            <li key={s.id}>
              <Icon size={14} aria-hidden="true" />
              <span className="sources__label mono">{s.label}</span>
              {s.kind !== 'knowledge' && <Tag muted>{t('chat.mockTag')}</Tag>}
              {s.detail && <span className="sources__detail">{s.detail}</span>}
            </li>
          );
        })}
      </ul>
    </details>
  );
}
