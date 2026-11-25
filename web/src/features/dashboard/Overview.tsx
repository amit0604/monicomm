import type { Status } from "../../components/ui/StatusPill";
import { useText } from "../../text";
import { useApi, type Summary } from "./api";
import type { View } from "./DashboardPage";
import {
  Card,
  DataView,
  DemoBadge,
  DeviceStatusPill,
  Empty,
  EventTable,
  SeverityPill,
  STATUS_TONE,
  STATUSES,
} from "./parts";
import { Refresh } from "./Refresh";

function Tile(props: {
  label: string;
  value: number;
  note: string;
  tone: Status;
  onClick: () => void;
}) {
  return (
    <button type="button" className={`tile tone--${props.tone}`} onClick={props.onClick}>
      <span className="muted">{props.label}</span>
      <span className="tile__value">{props.value}</span>
      <span className="tile__note">{props.note}</span>
    </button>
  );
}

export function Overview(props: { onView: (view: View) => void; onDevice: (id: string) => void }) {
  const { t, relative, absolute } = useText();
  const loaded = useApi<Summary>("/summary");
  const devicesWith = (status?: string) => () => props.onView({ tab: "devices", status });
  return (
    <>
      <div className="dash__bar">
        {loaded.data?.source === "demo" && <DemoBadge />}
        <Refresh loaded={loaded} />
      </div>
      <DataView loaded={loaded}>
        {({ devices: { total, by_status: s }, open_alerts: alerts, recent_events }) => (
          <>
            <div className="tiles">
              <Tile
                tone="info"
                label={t("total_devices")}
                value={total}
                note={`${s.warning + s.critical} ${t("with_issues")}`}
                onClick={devicesWith()}
              />
              <Tile
                tone="ok"
                label={t("online_devices")}
                value={s.online}
                note={`${t("of")} ${total}`}
                onClick={devicesWith("online")}
              />
              <Tile
                tone="accent"
                label={t("disconnected")}
                value={s.offline + s.suspected_offline}
                note={`${s.offline} ${t("offline_note")} · ${s.suspected_offline} ${t("suspected_note")}`}
                onClick={devicesWith("disconnected")}
              />
              <Tile
                tone="critical"
                label={t("open_alerts")}
                value={alerts.length}
                note={`${alerts.filter((a) => a.severity === "critical").length} ${t("critical_note")}`}
                onClick={() => document.getElementById("alerts")?.scrollIntoView()}
              />
            </div>
            <div className="dash__columns">
              <Card title={t("status_overview")}>
                <div className="bars">
                  {STATUSES.map((status) => {
                    const pct = total ? Math.round((s[status] / total) * 100) : 0;
                    return (
                      <button
                        key={status}
                        type="button"
                        className={`bar tone--${STATUS_TONE[status]}`}
                        title={`${t(`s_${status}`)}: ${s[status]} (${pct}%)`}
                        onClick={devicesWith(status)}
                      >
                        <span>
                          <DeviceStatusPill status={status} />
                        </span>
                        <span className="bar__track">
                          {s[status] > 0 && (
                            <span className="bar__fill" style={{ width: `${pct}%` }} />
                          )}
                        </span>
                        <span className="num">
                          <strong>{s[status]}</strong> ({pct}%)
                        </span>
                      </button>
                    );
                  })}
                </div>
              </Card>
              <div id="alerts">
                <Card title={t("open_alerts")}>
                  {alerts.length === 0 && <Empty title={t("no_alerts")} />}
                  <ul className="alerts">
                    {alerts.map((a) => (
                      <li key={a.id}>
                        <button
                          type="button"
                          className={`alerts__row tone--${a.severity}`}
                          onClick={() => props.onDevice(a.device_id)}
                        >
                          <SeverityPill group={a.severity} />
                          <span className="alerts__text">
                            {t(`a_${a.code}`)}
                            <bdi className="muted">{a.device_name}</bdi>
                          </span>
                          <span className="muted nowrap" title={absolute(a.opened_at)}>
                            {relative(a.opened_at)}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>
            </div>
            <Card
              title={t("recent_events")}
              extra={
                <button
                  type="button"
                  className="link push"
                  onClick={() => props.onView({ tab: "events" })}
                >
                  {t("view_all")}
                </button>
              }
            >
              <EventTable events={recent_events} onDevice={props.onDevice} />
            </Card>
          </>
        )}
      </DataView>
    </>
  );
}
