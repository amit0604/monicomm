import { CircleAlert, CircleCheck, CircleHelp, Info, Sparkles, TriangleAlert } from "lucide-react";

export type Status = "ok" | "warning" | "critical" | "info" | "neutral" | "accent";

const ICONS = {
  ok: CircleCheck,
  warning: TriangleAlert,
  critical: CircleAlert,
  info: Info,
  neutral: CircleHelp,
  accent: Sparkles,
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

/** Syslog severity → status color (PROJECT.md 6A). */
export function severityToStatus(severity: string): Status {
  switch (severity) {
    case "emerg":
    case "alert":
    case "crit":
      return "critical";
    case "err":
    case "warning":
      return "warning";
    case "notice":
    case "info":
      return "info";
    default:
      return "neutral";
  }
}
