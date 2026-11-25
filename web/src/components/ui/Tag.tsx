import type { ReactNode } from "react";

export function Tag({ children, muted = false }: { children: ReactNode; muted?: boolean }) {
  return <span className={muted ? "tag tag--muted" : "tag"}>{children}</span>;
}
