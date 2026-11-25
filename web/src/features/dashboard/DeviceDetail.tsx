import { Button, EmptyState, Panel } from "../../components/ui";
import type { ReactNode } from "react";
import { StatusPill } from "../../components/ui/StatusPill";
import { useText } from "./text";
import { useApi, type DeviceView, type NetInterface } from "./api";
import { DataView, DemoBadge, DeviceStatusPill, EventTable } from "./parts";
import { Refresh } from "./Refresh";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function InterfaceStatus({ i }: { i: NetInterface }) {
  const { t } = useText();
  if (i.admin_status === "down") return <StatusPill status="neutral" label={t("if_disabled")} />;
  return i.oper_status === "up" ? (
    <StatusPill status="ok" label={t("if_up")} />
  ) : (
    <StatusPill status="critical" label={t("if_down")} />
  );
}

function Meter({ value }: { value: number | null }) {
  if (value === null) return <span className="muted">—</span>;
  return (
    <span className="meter tone--info">
      <span className="bar__track">
        <span className="bar__fill" style={{ width: `${Math.min(100, value)}%` }} />
      </span>
      <bdi className="num">{value}%</bdi>
    </span>
  );
}

export function DeviceDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const { t, relative, absolute } = useText();
  const loaded = useApi<DeviceView>(`/devices/${encodeURIComponent(id)}`);
  const text = (v: string | null) =>
    v ? <bdi>{v}</bdi> : <span className="muted">{t("unknown")}</span>;
  const metric = (v: number | null, unit: string) =>
    v === null ? (
      <span className="muted">{t("no_data")}</span>
    ) : (
      <bdi>
        {v}
        {unit}
      </bdi>
    );
  const speed = (mbps: number | null) =>
    mbps === null ? "—" : mbps >= 1000 ? `${mbps / 1000} Gb/s` : `${mbps} Mb/s`;
  return (
    <>
      <div className="dash__bar">
        <Button onClick={onBack}>{t("back")}</Button>
        {loaded.data?.source === "demo" && <DemoBadge />}
        <Refresh loaded={loaded} />
      </div>
      <DataView loaded={loaded}>
        {({ device: d, events }) => (
          <>
            <div className="dash__bar">
              <h2 className="dash__title">
                <bdi>{d.name ?? d.ip}</bdi>
              </h2>
              <DeviceStatusPill status={d.status} />
            </div>
            <div className="dash__columns">
              <Panel flush title={t("information")}>
                <dl className="facts">
                  <Fact label={t("ip")}>
                    <bdi className="mono">{d.ip}</bdi>
                  </Fact>
                  <Fact label={t("type")}>{t(`t_${d.type}`)}</Fact>
                  <Fact label={t("vendor")}>{text(d.vendor)}</Fact>
                  <Fact label={t("model")}>{text(d.model)}</Fact>
                  <Fact label={t("os")}>{text(d.os_version)}</Fact>
                  <Fact label={t("serial")}>{text(d.serial)}</Fact>
                  <Fact label={t("site")}>
                    {d.site ?? <span className="muted">{t("unassigned")}</span>}
                  </Fact>
                  <Fact label={t("last_poll")}>
                    {d.last_poll_at ? (
                      <span title={absolute(d.last_poll_at)}>{relative(d.last_poll_at)}</span>
                    ) : (
                      text(null)
                    )}
                  </Fact>
                </dl>
              </Panel>
              <Panel flush title={t("metrics")}>
                <dl className="facts">
                  <Fact label={t("cpu")}>{metric(d.metrics.cpu_pct, "%")}</Fact>
                  <Fact label={t("memory")}>{metric(d.metrics.memory_pct, "%")}</Fact>
                  <Fact label={t("temperature")}>{metric(d.metrics.temperature_c, "°C")}</Fact>
                  <Fact label={t("uptime")}>
                    {d.metrics.uptime_seconds === null
                      ? metric(null, "")
                      : `${Math.floor(d.metrics.uptime_seconds / 86_400)} ${t("days")}`}
                  </Fact>
                </dl>
              </Panel>
            </div>
            <Panel flush title={t("interfaces")}>
              {d.interfaces.length === 0 ? (
                <EmptyState title={t("no_interfaces")} />
              ) : (
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>{t("interface")}</th>
                        <th>{t("status")}</th>
                        <th>{t("speed")}</th>
                        <th>{t("util_in")}</th>
                        <th>{t("util_out")}</th>
                        <th>{t("errors")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.interfaces.map((i) => (
                        <tr key={i.if_index}>
                          <td className="nowrap">
                            <bdi className="mono">{i.name}</bdi>{" "}
                            <bdi className="muted">{i.alias}</bdi>
                          </td>
                          <td>
                            <InterfaceStatus i={i} />
                          </td>
                          <td className="nowrap">
                            <bdi>{speed(i.speed_mbps)}</bdi>
                          </td>
                          <td>
                            <Meter value={i.in_util_pct} />
                          </td>
                          <td>
                            <Meter value={i.out_util_pct} />
                          </td>
                          <td className="num">
                            <bdi>
                              {i.in_errors ?? "—"} / {i.out_errors ?? "—"}
                            </bdi>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
            <Panel flush title={t("device_events")}>
              <EventTable events={events} />
            </Panel>
          </>
        )}
      </DataView>
    </>
  );
}
