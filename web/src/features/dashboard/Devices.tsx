import { useState } from "react";
import { useText } from "../../text";
import { query, useApi, type DeviceList, type DeviceType } from "./api";
import { SearchField, SelectField } from "./Filters";
import { Card, DataView, DemoBadge, DeviceStatusPill, Empty, STATUS_TONE, STATUSES } from "./parts";
import { Refresh } from "./Refresh";

const TYPES: DeviceType[] = ["router", "switch", "firewall", "server", "access_point", "unknown"];
const NONE = { q: "", status: "", type: "", vendor: "" };

export function Devices(props: { initialStatus?: string; onDevice: (id: string) => void }) {
  const { t } = useText();
  const [filters, setFilters] = useState({ ...NONE, status: props.initialStatus ?? "" });
  const loaded = useApi<DeviceList>(`/devices${query(filters)}`);
  const set = (key: keyof typeof NONE) => (value: string) =>
    setFilters((f) => ({ ...f, [key]: value }));
  const unknown = <span className="muted">{t("unknown")}</span>;
  const clear = Object.values(filters).some(Boolean) && (
    <button type="button" className="button" onClick={() => setFilters(NONE)}>
      {t("clear")}
    </button>
  );
  return (
    <>
      <div className="dash__bar">
        {loaded.data?.source === "demo" && <DemoBadge />}
        <Refresh loaded={loaded} />
      </div>
      <div className="filters">
        <SearchField value={filters.q} onChange={set("q")} label={t("search_devices")} />
        <SelectField
          value={filters.status}
          onChange={set("status")}
          label={t("all_statuses")}
          options={[
            ...STATUSES.map((s): [string, string] => [s, t(`s_${s}`)]),
            ["disconnected", t("disconnected")],
          ]}
        />
        <SelectField
          value={filters.type}
          onChange={set("type")}
          label={t("all_types")}
          options={TYPES.map((x) => [x, t(`t_${x}`)])}
        />
        <SelectField
          value={filters.vendor}
          onChange={set("vendor")}
          label={t("all_vendors")}
          options={(loaded.data?.vendors ?? []).map((v) => [v, v])}
        />
        {clear}
      </div>
      <DataView loaded={loaded}>
        {({ items, total }) => (
          <Card
            title={t("devices")}
            extra={
              <span className="muted" role="status">
                {t("showing")} {items.length} {t("of")} {total}
              </span>
            }
          >
            {items.length === 0 ? (
              <Empty title={t("no_results")} action={clear} />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>{t("name")}</th>
                      <th>{t("ip")}</th>
                      <th>{t("vendor")}</th>
                      <th>{t("model")}</th>
                      <th>{t("type")}</th>
                      <th>{t("status")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((d) => (
                      <tr key={d.id} className="table__row" onClick={() => props.onDevice(d.id)}>
                        <td className={`table__stripe nowrap tone--${STATUS_TONE[d.status]}`}>
                          <button type="button" className="link">
                            <bdi>{d.name ?? d.ip}</bdi>
                          </button>
                        </td>
                        <td className="mono">
                          <bdi>{d.ip}</bdi>
                        </td>
                        <td>{d.vendor ?? unknown}</td>
                        <td className="nowrap">{d.model ? <bdi>{d.model}</bdi> : unknown}</td>
                        <td className="nowrap">{t(`t_${d.type}`)}</td>
                        <td>
                          <DeviceStatusPill status={d.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}
      </DataView>
    </>
  );
}
