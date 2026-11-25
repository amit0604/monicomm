import type { ReactNode } from "react";
import { CircleAlert, Inbox, RotateCw, Sparkles } from "lucide-react";
import { Button } from "./Button";

// The three data states every view needs (PROJECT.md 6A): loading, empty, error.

export function Skeleton({ rows = 3, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="skeleton" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton__row" />
      ))}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state">
      <Inbox size={20} aria-hidden="true" />
      <p className="state__title">{title}</p>
      {children}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state state--error" role="alert">
      <CircleAlert size={20} aria-hidden="true" />
      <p className="state__title">{message}</p>
      {onRetry && (
        <Button onClick={onRetry}>
          <RotateCw size={16} aria-hidden="true" />
          Retry
        </Button>
      )}
    </div>
  );
}

// Marks AI-generated content (PROJECT.md 6A: "AI" tag + Sources list).
export function AiTag() {
  return (
    <span className="ai-tag">
      <Sparkles size={12} aria-hidden="true" />
      AI
    </span>
  );
}
