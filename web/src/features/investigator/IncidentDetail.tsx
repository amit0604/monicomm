import { Button, AiTag, ErrorState, Skeleton, StatusPill, type Status } from "../../components/ui";
import { useCallback, useEffect, useState } from "react";
import { Lock, LockOpen, Save, Sparkles, X } from "lucide-react";
import {
  analyzeIncident,
  ApiError,
  getIncident,
  patchIncident,
  type Incident,
  type IncidentPatch,
  type IncidentStatus,
  type Severity,
} from "./api";

export const STATUS_PILL: Record<IncidentStatus, { status: Status; label: string }> = {
  open: { status: "accent", label: "Open" },
  recovered: { status: "ok", label: "Recovered" },
  closed: { status: "neutral", label: "Closed" },
};

export const SEVERITY_PILL: Record<Severity, { status: Status; label: string }> = {
  critical: { status: "critical", label: "Critical" },
  warning: { status: "warning", label: "Warning" },
};

export const formatTime = (iso: string) => new Date(iso).toLocaleString();

const errorText = (e: unknown) => (e instanceof Error ? e.message : "Unknown error");

export function IncidentDetail({
  id,
  onClose,
  onChanged,
}: {
  id: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [incident, setIncident] = useState<Incident | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [resolution, setResolution] = useState("");
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const inc = await getIncident(id);
      setIncident(inc);
      setNotes(inc.notes);
      setResolution(inc.resolution);
    } catch (e) {
      setLoadError(errorText(e));
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save(body: IncidentPatch) {
    setBusy(true);
    setSaveError(null);
    try {
      await patchIncident(id, body);
      await load();
      onChanged();
    } catch (e) {
      setSaveError(`Could not save. ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function analyze() {
    setAnalyzing(true);
    setAnalysisError(null);
    try {
      const analysis = await analyzeIncident(id);
      setIncident((inc) => inc && { ...inc, analysis });
    } catch (e) {
      setAnalysisError(
        e instanceof ApiError && e.status === 503
          ? "The local model is not available right now. The incident data above is still valid; try again later."
          : `Analysis failed. ${errorText(e)}`,
      );
    } finally {
      setAnalyzing(false);
    }
  }

  const header = (
    <header className="detail__header">
      <h2 className="detail__title">{incident?.title ?? "Incident"}</h2>
      <Button variant="ghost" onClick={onClose} aria-label="Close details">
        <X size={16} aria-hidden="true" />
      </Button>
    </header>
  );

  if (!incident) {
    return (
      <aside className="panel detail" aria-label="Incident details">
        {header}
        {loadError ? (
          <ErrorState message={`Could not load the incident. ${loadError}`} onRetry={load} />
        ) : (
          <Skeleton rows={6} label="Loading incident" />
        )}
      </aside>
    );
  }

  const sources = new Set(incident.analysis?.sources ?? []);
  const eventsById = new Map(incident.timeline.map((ev) => [ev.id, ev]));
  const closed = incident.status === "closed";

  return (
    <aside className="panel detail" aria-label="Incident details">
      {header}
      <div className="detail__meta">
        <StatusPill {...SEVERITY_PILL[incident.severity]} />
        <StatusPill {...STATUS_PILL[incident.status]} />
        <span className="mono">{incident.devices.join(", ")}</span>
        <time dateTime={incident.started_at}>{formatTime(incident.started_at)}</time>
      </div>

      <section className="detail__section">
        <h3>Root cause</h3>
        {incident.root_cause ? (
          <div className="detail__row">
            <p>{incident.root_cause.summary}</p>
            <StatusPill status="info" label={`Confidence: ${incident.root_cause.confidence}`} />
          </div>
        ) : (
          <p className="muted">No root cause found yet.</p>
        )}
        {incident.possible_causes.length > 0 && (
          <>
            <h4>Possible causes</h4>
            <ul>
              {incident.possible_causes.map((c) => (
                <li key={c.summary}>{c.summary}</li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="detail__section">
        <h3>Impact</h3>
        {incident.impact.length === 0 ? (
          <p className="muted">No other devices affected.</p>
        ) : (
          <ul className="impact">
            {incident.impact.map((it, i) => (
              <li key={i} className="impact__item">
                <span className="mono">
                  {it.device}
                  {it.interface && ` ${it.interface}`}
                </span>
                <span>{it.what}</span>
                {it.recovered ? (
                  <StatusPill status="ok" label="Recovered" />
                ) : (
                  <StatusPill status="critical" label="Affected" />
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="detail__section">
        <div className="detail__row">
          <h3>AI explanation</h3>
          <Button variant="primary" onClick={analyze} disabled={analyzing}>
            <Sparkles size={16} aria-hidden="true" />
            {analyzing ? "Analyzing…" : "Analyze with AI"}
          </Button>
        </div>
        {analysisError && (
          <p className="detail__error" role="alert">
            {analysisError}
          </p>
        )}
        {incident.analysis && (
          <div className="analysis">
            <AiTag />
            <p>{incident.analysis.summary}</p>
            {incident.analysis.root_cause && (
              <p>
                <strong>Root cause:</strong> {incident.analysis.root_cause}
              </p>
            )}
            {incident.analysis.impact && (
              <p>
                <strong>Impact:</strong> {incident.analysis.impact}
              </p>
            )}
            <h4>Sources</h4>
            <ul className="analysis__sources">
              {incident.analysis.sources.map((sid) => {
                const ev = eventsById.get(sid);
                return (
                  <li key={sid}>
                    <a href={`#ev-${sid}`} className="mono">
                      {ev ? `${ev.device} ${ev.code ?? ev.type}` : sid}
                    </a>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </section>

      <section className="detail__section">
        <h3>Timeline</h3>
        <table className="timeline">
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">Device</th>
              <th scope="col">Code</th>
              <th scope="col">Raw</th>
            </tr>
          </thead>
          <tbody>
            {incident.timeline.map((ev) => (
              <tr
                key={ev.id}
                id={`ev-${ev.id}`}
                className={sources.has(ev.id) ? "timeline__row--source" : undefined}
                data-source={sources.has(ev.id) || undefined}
              >
                <td className="timeline__time">{formatTime(ev.ts)}</td>
                <td className="mono">{ev.hostname ?? ev.device}</td>
                <td className="mono">{ev.code ?? `${ev.type} ${ev.state ?? ""}`}</td>
                <td className="mono timeline__raw">{ev.raw}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="detail__section">
        <h3>Notes and resolution</h3>
        <label className="field">
          Notes
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
        </label>
        <label className="field">
          Resolution
          <textarea value={resolution} onChange={(e) => setResolution(e.target.value)} rows={2} />
        </label>
        {saveError && (
          <p className="detail__error" role="alert">
            {saveError}
          </p>
        )}
        <div className="detail__actions">
          <Button onClick={() => save({ notes, resolution })} disabled={busy}>
            <Save size={16} aria-hidden="true" />
            Save
          </Button>
          <Button
            variant={closed ? "secondary" : "danger"}
            onClick={() => save({ notes, resolution, status: closed ? "open" : "closed" })}
            disabled={busy}
          >
            {closed ? (
              <LockOpen size={16} aria-hidden="true" />
            ) : (
              <Lock size={16} aria-hidden="true" />
            )}
            {closed ? "Reopen" : "Close incident"}
          </Button>
        </div>
      </section>
    </aside>
  );
}
