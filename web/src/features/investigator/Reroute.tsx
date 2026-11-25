import { ErrorState, StatusPill, type Status } from "../../components/ui";
import type { Hop, HopStatus, Reroute as RerouteData, RerouteFlow, RoutePath } from "./api";

// Rerouting section of the incident detail (reroute-plan.md D6, D7). Recommendation only:
// Monicomm never changes device config (CLAUDE.md rule 3).

const HOP_PILL: Record<HopStatus, { status: Status; label: string }> = {
  ok: { status: "ok", label: "OK" },
  warning: { status: "warning", label: "Warning" },
  critical: { status: "critical", label: "Critical" },
  unknown: { status: "neutral", label: "Unknown" },
};

// D7: no utilization means we can't see it, so it is unknown, never ok.
const hopStatus = (h: Hop): HopStatus => (h.util_after == null ? "unknown" : h.status);

export function formatRate(bps: number | null): string {
  if (bps == null) return "Unknown";
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

interface Row {
  label: string;
  hops: Hop[] | null; // null = no path
  failed?: boolean;
}

function PathDiagram({ flow }: { flow: RerouteFlow }) {
  const rows: Row[] = [
    { label: "Before", hops: flow.before.hops, failed: true },
    { label: "Predicted", hops: flow.predicted?.hops ?? null },
  ];
  if (flow.recommended) rows.push({ label: "Recommended", hops: flow.recommended.hops });

  const maxNodes = Math.max(2, ...rows.map((r) => nodes(r.hops ?? []).length));
  const width = LEFT + (maxNodes - 1) * STEP + 60;
  const height = rows.length * ROW_H + 8;
  const describe = rows
    .map((r) =>
      r.hops
        ? `${r.label}: ${nodes(r.hops).join(" to ")}${r.failed ? " (down)" : ""}`
        : `${r.label}: no path`,
    )
    .join(". ");

  return (
    <svg
      className="reroute-graph"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Path diagram. ${describe}.`}
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
                No path
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
                    <text className="reroute-graph__label" x={x(i)} y={y + 22} textAnchor="middle">
                      {n}
                    </text>
                  </g>
                ))}
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ---- Hop table ------------------------------------------------------------------------------

function HopTable({ path, caption }: { path: RoutePath; caption: string }) {
  return (
    <table className="reroute-hops">
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th scope="col">Hop</th>
          <th scope="col">Speed</th>
          <th scope="col">Utilization after</th>
          <th scope="col">Status</th>
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
                {h.speed_mbps == null ? "Unknown" : formatRate(h.speed_mbps * 1e6)}
              </td>
              <td>
                {h.util_after == null ? (
                  <span className="muted">Unknown</span>
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
                <StatusPill {...HOP_PILL[status]} />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Flow({ flow }: { flow: RerouteFlow }) {
  return (
    <div className="reroute-flow">
      <p>{flow.reason}</p>
      <p className="muted">
        Moved load: {flow.load_bps == null ? "unknown" : formatRate(flow.load_bps)}
      </p>
      <PathDiagram flow={flow} />
      {flow.predicted ? (
        <HopTable path={flow.predicted} caption="Predicted path (lowest estimated cost)" />
      ) : (
        <ErrorState message="No alternative path: the two ends are cut off" />
      )}
      {flow.recommended && (
        <div className="reroute-flow__recommended">
          <HopTable path={flow.recommended} caption="Recommended path" />
          <p>{flow.recommended.why}</p>
          <p className="reroute-flow__note">
            Recommendation only — apply changes through your normal change process.
          </p>
        </div>
      )}
    </div>
  );
}

export function Reroute({ reroute }: { reroute: RerouteData }) {
  return (
    <section className="detail__section" aria-labelledby="reroute-title">
      <h3 id="reroute-title">Rerouting</h3>
      {reroute.flows.map((f, i) => (
        <Flow key={i} flow={f} />
      ))}
      {reroute.isolated.length > 0 && (
        <>
          <h4>Cut off from the network</h4>
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
          <h4>Based on</h4>
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
