import { FlaskConical, RotateCw, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { StatusPill, type Status } from "../../components/ui/StatusPill";
import { useText } from "../../text";
import type { DeviceStatus, Loaded, NetworkEvent, SeverityGroup } from "./api";

export const STATUS_TONE: Record<DeviceStatus, Status> = {
  online: "ok",
  warning: "warning",
  critical: "critical",
  suspected_offline: "accent",
  offline: "neutral",
};
export const STATUSES = Object.keys(STATUS_TONE) as DeviceStatus[];
export const SEVERITIES: SeverityGroup[] = ["critical", "warning", "info", "neutral"];

export function DeviceStatusPill({ status }: { status: DeviceStatus }) {
  const { t } = useText();
  return <StatusPill status={STATUS_TONE[status]} label={t(`s_${status}`)} />;
}

export function SeverityPill({ group }: { group: SeverityGroup }) {
  const { t } = useText();
  return <StatusPill status={group} label={t(`g_${group}`)} />;
}

export function DemoBadge() {
  const { t } = useText();
  return (
    <span className="demo-badge" role="note">
      <FlaskConical size={16} aria-hidden="true" />
      <strong>DEMO</strong>
      {t("demo")}
    </span>
  );
}

export function Card(props: {
  title: string;
  extra?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`card ${props.className ?? ""}`}>
      <header className="card__head">
        <h2>{props.title}</h2>
        {props.extra}
      </header>
      {props.children}
    </section>
  );
}

export function Empty({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="state">
      <strong>{title}</strong>
      {action}
    </div>
  );
}

/** Loading skeleton, error with retry, or the data (with a notice when the last refresh failed). */
export function DataView<T>(props: { loaded: Loaded<T>; children: (data: T) => ReactNode }) {
  const { t } = useText();
  const { data, error, reload } = props.loaded;
  if (data !== null) {
    return (
      <>
        {error !== null && (
          <p className="banner" role="status">
            <TriangleAlert size={16} aria-hidden="true" />
            {t("stale")}
          </p>
        )}
        {props.children(data)}
      </>
    );
  }
  if (error !== null) {
    return (
      <div className="card state" role="alert">
        <strong>{t(error === 503 ? "no_source" : error === 404 ? "not_found" : "failed")}</strong>
        <button type="button" className="button" onClick={reload}>
          <RotateCw size={16} aria-hidden="true" />
          {t("retry")}
        </button>
      </div>
    );
  }
  return (
    <div role="status" className="skeleton">
      <span className="sr-only">{t("loading")}</span>
    </div>
  );
}

export function EventTable(props: { events: NetworkEvent[]; onDevice?: (id: string) => void }) {
  const { t, relative, absolute } = useText();
  if (props.events.length === 0) return <Empty title={t("no_events")} />;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>{t("severity")}</th>
            <th>{t("time")}</th>
            {props.onDevice && <th>{t("device")}</th>}
            <th>{t("origin")}</th>
            <th>{t("message")}</th>
          </tr>
        </thead>
        <tbody>
          {props.events.map((e) => (
            <tr key={e.id}>
              <td className={`table__stripe tone--${e.severity_group}`}>
                <SeverityPill group={e.severity_group} />
              </td>
              <td className="nowrap" title={absolute(e.received_at)}>
                {relative(e.received_at)}
              </td>
              {props.onDevice && (
                <td className="nowrap">
                  {e.device_id ? (
                    <button
                      type="button"
                      className="link"
                      onClick={() => props.onDevice?.(e.device_id!)}
                    >
                      <bdi>{e.device_name ?? e.source_ip}</bdi>
                    </button>
                  ) : (
                    <bdi className="mono">{e.source_ip}</bdi>
                  )}
                </td>
              )}
              <td className="nowrap">{e.kind === "syslog" ? "Syslog" : "SNMP trap"}</td>
              <td className="mono message">
                <bdi dir="ltr">{e.message}</bdi>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
