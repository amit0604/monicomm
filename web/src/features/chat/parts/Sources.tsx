import { Bell, FileCode2, HardDrive, LineChart, ScrollText, Table2 } from 'lucide-react';
import { useI18n } from '../../../i18n';
import type { Source } from '../types';

const ICONS = {
  device: HardDrive,
  log: ScrollText,
  metric: LineChart,
  config: FileCode2,
  alert: Bell,
  inventory: Table2,
} as const;

/** Evidence or it didn't happen (PROJECT.md AI rule 4): every AI answer lists what it was based on. */
export function Sources({ sources }: { sources: Source[] }) {
  const { t } = useI18n();
  if (sources.length === 0) return null;
  return (
    <details className="sources">
      <summary>
        {t('chat.sources')} <span className="num">({sources.length})</span>
      </summary>
      <ul>
        {sources.map((s) => {
          const Icon = ICONS[s.kind];
          return (
            <li key={s.id}>
              <Icon size={14} aria-hidden="true" />
              <span className="mono">{s.label}</span>
              {s.detail && <span className="sources__detail">{s.detail}</span>}
            </li>
          );
        })}
      </ul>
    </details>
  );
}
