import { EmptyState, ErrorState, Skeleton, StatusPill } from "../../components/ui";
import type { IncidentStatus, IncidentSummary } from "./api";
import { formatTime, IncidentDetail, SEVERITY_PILL, STATUS_PILL } from "./IncidentDetail";
import { useIncidentList } from "./useIncidents";
import "./investigator.css";

const GROUPS: IncidentStatus[] = ["open", "recovered", "closed"];

export function InvestigatorPage({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const { data, error, loading, reload } = useIncidentList();

  let body;
  if (!data && loading) body = <Skeleton rows={4} label="Loading incidents" />;
  else if (!data)
    body = <ErrorState message={`Could not load incidents. ${error}`} onRetry={reload} />;
  else if (data.length === 0)
    body = (
      <EmptyState
        title="No abnormal events. The network looks normal."
        body="New incidents appear here automatically."
      />
    );
  else
    body = GROUPS.map((g) => (
      <IncidentGroup
        key={g}
        status={g}
        items={data.filter((i) => i.status === g)}
        selectedId={selectedId}
        onSelect={onSelect}
      />
    ));

  return (
    <div className={selectedId ? "investigator investigator--split" : "investigator"}>
      <section className="panel" aria-label="Incidents">
        {body}
      </section>
      {selectedId && (
        <IncidentDetail
          key={selectedId}
          id={selectedId}
          onClose={() => onSelect(null)}
          onChanged={reload}
        />
      )}
    </div>
  );
}

function IncidentGroup({
  status,
  items,
  selectedId,
  onSelect,
}: {
  status: IncidentStatus;
  items: IncidentSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (items.length === 0) return null;
  const pill = STATUS_PILL[status];
  return (
    <div className={`board-group board-group--${pill.status}`}>
      <h2 className="board-group__title">
        {pill.label} <span className="board-group__count">{items.length}</span>
      </h2>
      <ul className="board-group__list">
        {items.map((inc) => (
          <li key={inc.id}>
            <button
              type="button"
              className="board-row"
              aria-current={inc.id === selectedId ? "true" : undefined}
              onClick={() => onSelect(inc.id)}
            >
              <StatusPill {...SEVERITY_PILL[inc.severity]} />
              <StatusPill {...STATUS_PILL[inc.status]} />
              <span className="board-row__title">{inc.title}</span>
              <span className="mono board-row__devices">{inc.devices.join(", ")}</span>
              <time className="board-row__time" dateTime={inc.started_at}>
                {formatTime(inc.started_at)}
              </time>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
