import { CircleAlert, RotateCw, Sparkles } from "lucide-react";
import { Button } from "./Button";

// Loading and error states (PROJECT.md 6A). The empty state is EmptyState.tsx.

export function Skeleton({ rows = 3, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="skeleton-group" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton skeleton--row" />
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="empty empty--error" role="alert">
      <div className="empty__icon" aria-hidden="true">
        <CircleAlert size={28} />
      </div>
      <p className="empty__title">{message}</p>
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
