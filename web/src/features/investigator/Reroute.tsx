import { ErrorState, StatusPill, type Status } from "../../components/ui";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/en";
import type { Hop, HopStatus, Reroute as RerouteData, RerouteFlow, RoutePath } from "./api";

// Rerouting section of the incident detail (reroute-plan.md D6, D7). Recommendation only:
// Monicomm never changes device config (CLAUDE.md rule 3).

const HOP_PILL: Record<HopStatus, { status: Status; label: MessageKey }> = {
  ok: { status: "ok", label: "reroute.status.ok" },
  warning: { status: "warning", label: "reroute.status.warning" },
  critical: { status: "critical", label: "reroute.status.critical" },
  unknown: { status: "neutral", label: "reroute.status.unknown" },
};

// D7: no utilization means we can't see it, so it is unknown, never ok.
const hopStatus = (h: Hop): HopStatus => (h.util_after == null ? "unknown" : h.status);

export function formatRate(bps: number): string {
  if (bps >= 1e9) return `${+(bps / 1e9).toFixed(1)} Gbps`;
  if (bps >= 1e6) return `${+(bps / 1e6).toFixed(1)} Mbps`;
  if (bps >= 1e3) return `${+(bps / 1e3).toFixed(1)} kbps`;
  return `${Math.round(bps)} bps`;
}

const pct = (u: number) => `${Math.round(u * 100)} %`;
const nodes = (hops: Hop[]) => (hops.length ? [hops[0].from, ...hops.map((h) => h.to)] : []);

// ---- Path diagram ---------------------------------------------------------------------------

const ROW_H = 56;
const STEP = 140;
const LEFT = 110;
const MAX_LABEL = 18; // fits in STEP at the label font size
const short = (s: string) => (s.length > MAX_LABEL ? `${s.slice(0, MAX_LABEL - 1)}…` : s);

interface Row {
  label: string;
  hops: Hop[] | null; // null = no path
  failed?: boolean;
}

function PathDiagram({ flow }: { flow: RerouteFlow }) {
  const { t } = useI18n();
  const rows: Row[] = [
    { label: t("reroute.before"), hops: flow.before.hops, failed: true },
    { label: t("reroute.predicted"), hops: flow.predicted?.hops ?? null },
  ];
  if (flow.recommended) rows.push({ label: t("reroute.recommended"), hops: flow.recommended.hops });

  const maxNodes = Math.max(2, ...rows.map((r) => nodes(r.hops ?? []).length));
  const width = LEFT + (maxNodes - 1) * STEP + 60;
  const height = rows.length * ROW_H + 8;
  const describe = rows
    .map((r) => {
      if (!r.hops) return t("reroute.diagramNoPath", { label: r.label });
      const path = nodes(r.hops).join(t("reroute.pathSeparator"));
      return t(r.failed ? "reroute.diagramDown" : "reroute.diagramRow", { label: r.label, path });
    })
    .join(". ");

  // Natural size inside a scroll box, so long paths scroll instead of shrinking the text.
  return (
    <div className="reroute-graph-scroll">
      <svg
        className="reroute-graph"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={t("reroute.diagram", { rows: describe })}
      >
        {rows.map((r, ri) => {
          const y = ri * ROW_H + 24;
          const x = (i: number) => LEFT + i * STEP;
          return (
            <g key={r.label}>
              <text className="reroute-graph__row" x={0} y={y + 4}>
                {r.label}
              </text>
              {r.hops === null ? (
                <text className="reroute-graph__none" x={LEFT} y={y + 4}>
                  {t("reroute.noPath")}
                </text>
              ) : (
                <>
                  {r.hops.map((h, i) => (
                    <line
                      key={i}
                      className={`reroute-graph__edge reroute-graph__edge--${r.failed ? "failed" : hopStatus(h)}`}
                      x1={x(i)}
                      y1={y}
                      x2={x(i + 1)}
                      y2={y}
                    />
                  ))}
                  {nodes(r.hops).map((n, i) => (
                    <g key={i}>
                      <circle className="reroute-graph__node" cx={x(i)} cy={y} r={6} />
                      <text
                        className="reroute-graph__label"
                        x={x(i)}
                        y={y + 22}
                        textAnchor="middle"
                      >
                        <title>{n}</title>
                        {short(n)}
                      </text>
                    </g>
                  ))}
                </>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---- Hop table ------------------------------------------------------------------------------

function HopTable({ path, caption }: { path: RoutePath; caption: string }) {
  const { t } = useI18n();
  return (
    <table className="reroute-hops">
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th scope="col">{t("reroute.col.hop")}</th>
          <th scope="col">{t("reroute.col.speed")}</th>
          <th scope="col">{t("reroute.col.util")}</th>
          <th scope="col">{t("reroute.col.status")}</th>
        </tr>
      </thead>
      <tbody>
        {path.hops.map((h, i) => {
          const status = hopStatus(h);
          return (
            <tr key={i}>
              <td className="mono">
                {h.from} {h.from_if} → {h.to} {h.to_if}
              </td>
              <td className="reroute-hops__num">
                {h.speed_mbps == null ? t("reroute.unknown") : formatRate(h.speed_mbps * 1e6)}
              </td>
              <td>
                {h.util_after == null ? (
                  <span className="muted">{t("reroute.unknown")}</span>
                ) : (
                  <span className="reroute-util">
                    <span className="reroute-util__track" aria-hidden="true">
                      <span
                        className={`reroute-util__bar reroute-util__bar--${status}`}
                        style={{ width: `${Math.min(h.util_after, 1) * 100}%` }}
                      />
                    </span>
                    <span className="reroute-hops__num">{pct(h.util_after)}</span>
                  </span>
                )}
              </td>
              <td>
                <StatusPill status={HOP_PILL[status].status} label={t(HOP_PILL[status].label)} />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Flow({ flow }: { flow: RerouteFlow }) {
  const { t } = useI18n();
  return (
    <div className="reroute-flow">
      <p>{flow.reason}</p>
      <p className="muted">
        {t("reroute.movedLoad", {
          load: flow.load_bps == null ? t("reroute.loadUnknown") : formatRate(flow.load_bps),
        })}
      </p>
      <PathDiagram flow={flow} />
      {flow.predicted ? (
        <HopTable path={flow.predicted} caption={t("reroute.predictedCaption")} />
      ) : (
        <ErrorState message={t("reroute.cutOff")} />
      )}
      {flow.recommended && (
        <div className="reroute-flow__recommended">
          <HopTable path={flow.recommended} caption={t("reroute.recommendedCaption")} />
          <p>{flow.recommended.why}</p>
          <p className="reroute-flow__note">{t("reroute.recommendationOnly")}</p>
        </div>
      )}
    </div>
  );
}

export function Reroute({ reroute }: { reroute: RerouteData }) {
  const { t } = useI18n();
  return (
    <section className="detail__section" aria-labelledby="reroute-title">
      <h3 id="reroute-title">{t("reroute.title")}</h3>
      {reroute.flows.map((f, i) => (
        <Flow key={i} flow={f} />
      ))}
      {reroute.isolated.length > 0 && (
        <>
          <h4>{t("reroute.isolated")}</h4>
          <ul>
            {reroute.isolated.map((d) => (
              <li key={d} className="mono">
                {d}
              </li>
            ))}
          </ul>
        </>
      )}
      {reroute.assumptions.length > 0 && (
        <>
          <h4>{t("reroute.basedOn")}</h4>
          <ul className="reroute-assumptions">
            {reroute.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
