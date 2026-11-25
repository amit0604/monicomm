import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { listIncidents, type IncidentSummary } from "./api";

export const POLL_MS = 15_000;

interface ListState {
  data?: IncidentSummary[];
  error?: string;
  loading: boolean;
}

// Polls the incident list. Keeps the last good data if a later poll fails.
export function useIncidentList(intervalMs = POLL_MS) {
  const [state, setState] = useState<ListState>({ loading: true });

  const load = useCallback(async () => {
    try {
      const data = await listIncidents();
      setState({ data, loading: false });
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: e instanceof Error ? e.message : "Error" }));
    }
  }, []);

  const reload = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: undefined }));
    void load();
  }, [load]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), intervalMs);
    return () => clearInterval(timer);
  }, [load, intervalMs]);

  return { ...state, reload };
}

// Toasts once per NEW critical incident id. Incidents already present on the first
// successful load are remembered silently so a page refresh doesn't re-alert.
export function useCriticalIncidentToasts(onOpen: (id: string) => void, intervalMs = POLL_MS) {
  const { data } = useIncidentList(intervalMs);
  const seen = useRef<Set<string> | null>(null);
  const openRef = useRef(onOpen);
  openRef.current = onOpen;

  useEffect(() => {
    if (!data) return;
    const critical = data.filter((i) => i.severity === "critical");
    if (seen.current === null) {
      seen.current = new Set(critical.map((i) => i.id));
      return;
    }
    for (const inc of critical) {
      if (seen.current.has(inc.id)) continue;
      seen.current.add(inc.id);
      toast.error(inc.title, {
        id: inc.id,
        description: inc.devices.join(", "),
        duration: Infinity,
        action: { label: "Open", onClick: () => openRef.current(inc.id) },
      });
    }
  }, [data]);
}
