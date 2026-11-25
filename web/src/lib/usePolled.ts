import { useCallback, useEffect, useRef, useState } from "react";

const REFRESH_MS = 30_000;

interface State<T> {
  data: T | null;
  /** HTTP status, or 0 when the server could not be reached or sent something unexpected. */
  error: number | null;
  updatedAt: string | null;
}
export interface Polled<T> extends State<T> {
  reload: () => void;
}

const anyBody = () => true;

/**
 * Loads a URL, refreshes it every 30 seconds and keeps the last good data if a refresh fails.
 * `accept` rejects a body of the wrong shape (a proxy's error page, an old server); pass a
 * module-level function.
 */
export function usePolled<T>(url: string, accept: (body: unknown) => boolean = anyBody): Polled<T> {
  const [state, setState] = useState<State<T>>({ data: null, error: null, updatedAt: null });
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  const loadedUrl = useRef<string | null>(null);
  const acceptRef = useRef(accept);
  acceptRef.current = accept;

  useEffect(() => {
    const abort = new AbortController();
    const load = async () => {
      let error = 0;
      try {
        const res = await fetch(url, { signal: abort.signal });
        if (res.ok) {
          const data: unknown = await res.json();
          if (abort.signal.aborted) return;
          if (acceptRef.current(data)) {
            loadedUrl.current = url;
            setState({ data: data as T, error: null, updatedAt: new Date().toISOString() });
            return;
          }
        } else {
          error = res.status;
        }
      } catch {
        // Unreachable, or aborted because the view moved on.
      }
      if (abort.signal.aborted) return;
      // Data of another filter or device must not stay on screen as if it answered this request.
      setState((s) =>
        loadedUrl.current === url ? { ...s, error } : { data: null, error, updatedAt: null },
      );
    };
    void load();
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => {
      abort.abort();
      clearInterval(timer);
    };
  }, [url, attempt]);

  return { ...state, reload };
}
