import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

// The one empty state for every view (PROJECT.md 6A). Pass an icon to override the default.
export function EmptyState({
  icon = <Inbox size={28} />,
  title,
  body,
  children,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty__icon" aria-hidden="true">
        {icon}
      </div>
      <h2 className="empty__title">{title}</h2>
      {body && <p className="empty__body">{body}</p>}
      {children}
    </div>
  );
}
