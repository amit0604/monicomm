import type { ReactNode } from "react";

export function Panel({
  title,
  actions,
  children,
  className,
  flush = false,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Header bar with a divider and no body padding, for tables that run edge to edge. */
  flush?: boolean;
}) {
  return (
    <section className={["panel", flush && "panel--flush", className].filter(Boolean).join(" ")}>
      {(title || actions) && (
        <header className="panel__header">
          {title && <h2 className="panel__title">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}
