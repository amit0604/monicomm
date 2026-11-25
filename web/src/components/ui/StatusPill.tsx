import { AlertTriangle, CheckCircle2, CircleDashed, Info, OctagonAlert, Sparkles } from 'lucide-react';

export type Status = 'ok' | 'warning' | 'critical' | 'info' | 'neutral' | 'accent';

const ICONS = {
  ok: CheckCircle2,
  warning: AlertTriangle,
  critical: OctagonAlert,
  info: Info,
  neutral: CircleDashed,
  accent: Sparkles,
} as const;

/** Status is never color alone: color + icon + label (PROJECT.md 6A). */
export function StatusPill({ status, label }: { status: Status; label: string }) {
  const Icon = ICONS[status];
  return (
    <span className={`pill pill--${status}`}>
      <Icon size={12} aria-hidden="true" />
      {label}
    </span>
  );
}

/** Syslog severity → status color, per PROJECT.md 6A. */
export function severityToStatus(severity: string): Status {
  switch (severity) {
    case 'emerg':
    case 'alert':
    case 'crit':
      return 'critical';
    case 'err':
    case 'warning':
      return 'warning';
    case 'notice':
    case 'info':
      return 'info';
    default:
      return 'neutral';
  }
}
