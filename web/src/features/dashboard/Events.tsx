import { Button, Panel } from "../../components/ui";
import { useState } from "react";
import { useText } from "./text";
import { query, useApi, type EventList } from "./api";
import { SearchField, SelectField } from "./Filters";
import { DataView, DemoBadge, EventTable, SEVERITIES } from "./parts";
import { Refresh } from "./Refresh";

const NONE = { q: "", severity: "", kind: "" };

export function Events(props: { onDevice: (id: string) => void }) {
  const { t } = useText();
  const [filters, setFilters] = useState(NONE);
  const loaded = useApi<EventList>(`/events${query(filters)}`);
  const set = (key: keyof typeof NONE) => (value: string) =>
    setFilters((f) => ({ ...f, [key]: value }));
  return (
    <>
      <div className="dash__bar">
        {loaded.data?.source === "demo" && <DemoBadge />}
        <Refresh loaded={loaded} />
      </div>
      <div className="filters">
        <SearchField value={filters.q} onChange={set("q")} label={t("search_events")} />
        <SelectField
          value={filters.severity}
          onChange={set("severity")}
          label={t("all_severities")}
          options={SEVERITIES.map((g) => [g, t(`g_${g}`)])}
        />
        <SelectField
          value={filters.kind}
          onChange={set("kind")}
          label={t("all_kinds")}
          options={[
            ["syslog", "Syslog"],
            ["trap", "SNMP trap"],
          ]}
        />
        {Object.values(filters).some(Boolean) && (
          <Button onClick={() => setFilters(NONE)}>{t("clear")}</Button>
        )}
      </div>
      <DataView loaded={loaded}>
        {({ items, total }) => (
          <Panel
            flush
            title={t("events")}
            actions={
              <span className="muted" role="status">
                {t("showing")} {items.length} {t("of")} {total}
              </span>
            }
          >
            <EventTable events={items} onDevice={props.onDevice} />
          </Panel>
        )}
      </DataView>
    </>
  );
}
