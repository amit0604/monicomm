import { CircleAlert, CircleCheck, CircleDot, CircleHelp, Info, TriangleAlert } from "lucide-react";

export type Status = "ok" | "warning" | "critical" | "info" | "neutral" | "accent";

const ICONS = {
  ok: CircleCheck,
  warning: TriangleAlert,
  critical: CircleAlert,
  info: Info,
  neutral: CircleHelp,
  accent: CircleDot,
} as const;

// Status is always color + icon + text (PROJECT.md section 6A), never color alone.
export function StatusPill({ status, label }: { status: Status; label: string }) {
  const Icon = ICONS[status];
  return (
    <span className={`status-pill status-pill--${status}`} data-status={status}>
      <Icon size={12} aria-hidden="true" />
      {label}
    </span>
  );
}
