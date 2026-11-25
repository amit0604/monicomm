import { FlaskConical, TriangleAlert, X } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import type { MessageKey } from "../../i18n/en";
import { Button, ErrorState, Panel, Skeleton, StatusPill } from "../../components/ui";
import type { LinkStatus, MapLink, MapNode, Medium, Topology } from "./api";
import { LINK_STATUSES, MEDIUMS, useTopology } from "./api";
import {
  DEVICE_TONE,
  LINK_LINE,
  LINK_TONE,
  MEDIUM_TOKEN,
  countBy,
  neighbors,
  roots,
  shortPort,
  visibleLinks,
} from "./model";
import type { Filters } from "./model";
import { useMapText } from "./text";
import { TopologyGraph, type Selection } from "./TopologyGraph";
import "./mapper.css";

/** Mapper: the network as devices (nodes) and links (edges, with the port at each end). */
export function MapperPage({ theme }: { theme: string }) {
  const { t } = useMapText();
  const { data, error, reload } = useTopology();
  if (data)
    return (
      <>
        {error !== null && (
          <p className="mapper__banner" role="status">
            <TriangleAlert size={16} aria-hidden="true" />
            {t("stale")}
          </p>
        )}
        <MapperView topology={data} theme={theme} />
      </>
    );
  if (error !== null)
    return (
      <ErrorState
        message={t(error === 503 ? "no_source" : "failed")}
        onRetry={reload}
        retryLabel={t("retry")}
      />
    );
  return <Skeleton rows={6} label={t("loading")} />;
}

function MapperView({ topology, theme }: { topology: Topology; theme: string }) {
  const { t, raw } = useMapText();
  const [filters, setFilters] = useState<Filters>({ mediums: new Set(MEDIUMS), status: "" });
  const [selected, setSelected] = useState<Selection>(null);
  const links = useMemo(() => visibleLinks(topology, filters), [topology, filters]);
  const rootIds = useMemo(() => roots(topology), [topology]);
  const byId = useMemo(() => new Map(topology.nodes.map((n) => [n.id, n])), [topology]);
  const issues = countBy(topology.links.map((l) => l.status));

  const deviceLabel = useCallback(
    (n: MapNode) =>
      n.status === "online" ? n.name : `${n.name}\n${raw(`dash.s_${n.status}` as MessageKey)}`,
    [raw],
  );
  const linkLabel = useCallback((s: LinkStatus) => t(`l_${s}`), [t]);

  const toggleMedium = (m: Medium) =>
    setFilters((f) => {
      const mediums = new Set(f.mediums);
      if (mediums.has(m)) mediums.delete(m);
      else mediums.add(m);
      return { ...f, mediums };
    });

  return (
    <div className="mapper">
      <div className="mapper__bar">
        <span className="mapper__demo" role="note" hidden={topology.source !== "demo"}>
          <FlaskConical size={16} aria-hidden="true" />
          <strong>DEMO</strong>
          {t("demo")}
        </span>
        <span className="mapper__summary num">
          {t("summary", { devices: topology.nodes.length, links: topology.links.length })}
        </span>
        {(["down", "degraded", "unknown"] as const).map(
          (s) =>
            issues[s] && (
              <StatusPill key={s} status={LINK_TONE[s]} label={`${issues[s]} ${t(`l_${s}`)}`} />
            ),
        )}
      </div>

      {topology.unresolved_links > 0 && (
        <p className="mapper__banner" role="status">
          <TriangleAlert size={16} aria-hidden="true" />
          {t("unresolved", { count: topology.unresolved_links })}
        </p>
      )}

      <div className="mapper__filters">
        <fieldset className="mapper__mediums">
          <legend>{t("medium")}</legend>
          {MEDIUMS.map((m) => (
            <button
              key={m}
              type="button"
              className="mapper__chip"
              aria-pressed={filters.mediums.has(m)}
              onClick={() => toggleMedium(m)}
            >
              <Swatch medium={m} />
              {t(`m_${m}`)}
            </button>
          ))}
        </fieldset>
        <label className="mapper__select">
          {t("status")}
          <select
            value={filters.status}
            onChange={(e) =>
              setFilters((f) => ({ ...f, status: e.target.value as LinkStatus | "" }))
            }
          >
            <option value="">{t("allStatuses")}</option>
            {LINK_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`l_${s}`)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mapper__main">
        <Panel className="mapper__canvas">
          <TopologyGraph
            nodes={topology.nodes}
            links={links}
            roots={rootIds}
            selected={selected}
            onSelect={setSelected}
            theme={theme}
            label={t("graph")}
            deviceLabel={deviceLabel}
            linkLabel={linkLabel}
          />
          <Legend />
        </Panel>
        <Details
          topology={topology}
          byId={byId}
          selected={selected}
          onSelect={setSelected}
          onClose={() => setSelected(null)}
        />
      </div>

      <Panel title={t("links")} flush>
        {links.length === 0 ? (
          <p className="mapper__empty">{t("noMatch")}</p>
        ) : (
          <LinkTable links={links} byId={byId} selected={selected} onSelect={setSelected} />
        )}
      </Panel>
    </div>
  );
}

function Swatch({ medium }: { medium: Medium }) {
  return (
    <span
      className="mapper__swatch"
      style={{ borderColor: `var(${MEDIUM_TOKEN[medium]})` }}
      aria-hidden="true"
    />
  );
}

function Legend() {
  const { t } = useMapText();
  return (
    <section className="mapper__legend" aria-label={t("legend")}>
      <ul>
        {MEDIUMS.map((m) => (
          <li key={m}>
            <Swatch medium={m} />
            {t(`m_${m}`)}
          </li>
        ))}
      </ul>
      <ul aria-label={t("lineStyle")}>
        {LINK_STATUSES.map((s) => (
          <li key={s}>
            <span className={`mapper__line mapper__line--${LINK_LINE[s]}`} aria-hidden="true" />
            <StatusPill status={LINK_TONE[s]} label={t(`l_${s}`)} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function speed(mbps: number | null, t: ReturnType<typeof useMapText>["t"]): string {
  if (mbps === null) return "—";
  return mbps >= 1000 ? t("gbps", { n: mbps / 1000 }) : t("mbps", { n: mbps });
}

function LinkStatusPill({ link }: { link: MapLink }) {
  const { t } = useMapText();
  return <StatusPill status={LINK_TONE[link.status]} label={t(`l_${link.status}`)} />;
}

function End({ node, port }: { node: MapNode | undefined; port: string }) {
  return (
    <span className="mapper__end">
      <span className="mono">{node?.name ?? "?"}</span>
      <span className="mapper__port mono" dir="ltr">
        {shortPort(port)}
      </span>
    </span>
  );
}

function LinkTable(props: {
  links: MapLink[];
  byId: Map<string, MapNode>;
  selected: Selection;
  onSelect: (s: Selection) => void;
}) {
  const { t } = useMapText();
  return (
    <div className="mapper__table-wrap">
      <table className="mapper__table">
        <thead>
          <tr>
            <th scope="col">{t("from")}</th>
            <th scope="col">{t("to")}</th>
            <th scope="col">{t("medium")}</th>
            <th scope="col">{t("speed")}</th>
            <th scope="col">{t("status")}</th>
            <th scope="col">{t("reason")}</th>
          </tr>
        </thead>
        <tbody>
          {props.links.map((l) => {
            const active = props.selected?.kind === "link" && props.selected.id === l.id;
            return (
              <tr key={l.id} aria-selected={active} className={active ? "is-selected" : undefined}>
                <td>
                  <button
                    type="button"
                    className="mapper__row-btn"
                    onClick={() => props.onSelect({ kind: "link", id: l.id })}
                  >
                    <End node={props.byId.get(l.a.device_id)} port={l.a.port} />
                  </button>
                </td>
                <td>
                  <End node={props.byId.get(l.b.device_id)} port={l.b.port} />
                </td>
                <td>
                  <span className="mapper__medium">
                    <Swatch medium={l.medium} />
                    {t(`m_${l.medium}`)}
                  </span>
                </td>
                <td className="num">{speed(l.speed_mbps, t)}</td>
                <td>
                  <LinkStatusPill link={l} />
                </td>
                <td className="mapper__muted">{l.reason ? t(`r_${l.reason}`) : ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Details(props: {
  topology: Topology;
  byId: Map<string, MapNode>;
  selected: Selection;
  onSelect: (s: Selection) => void;
  onClose: () => void;
}) {
  const { t, raw } = useMapText();
  const { selected, byId } = props;
  const node = selected?.kind === "node" ? byId.get(selected.id) : undefined;
  const link =
    selected?.kind === "link" ? props.topology.links.find((l) => l.id === selected.id) : undefined;
  const close = (
    <Button variant="ghost" size="sm" iconOnly aria-label={t("close")} onClick={props.onClose}>
      <X size={16} aria-hidden="true" />
    </Button>
  );

  if (node) {
    const mine = neighbors(props.topology, node.id);
    return (
      <Panel className="mapper__details" title={node.name} actions={close}>
        <StatusPill
          status={DEVICE_TONE[node.status]}
          label={raw(`dash.s_${node.status}` as MessageKey)}
        />
        <dl className="mapper__facts">
          <dt>{t("type")}</dt>
          <dd>{raw(`dash.t_${node.type}` as MessageKey)}</dd>
          <dt>{t("ip")}</dt>
          <dd className="mono" dir="ltr">
            {node.ip}
          </dd>
          <dt>{t("vendor")}</dt>
          <dd>{[node.vendor, node.model].filter(Boolean).join(" ") || "—"}</dd>
          <dt>{t("site")}</dt>
          <dd>{node.site ?? "—"}</dd>
        </dl>
        <h3 className="mapper__subtitle">{t("deviceLinks")}</h3>
        {mine.length === 0 ? (
          <p className="mapper__muted">{t("noLinks")}</p>
        ) : (
          <ul className="mapper__neighbors">
            {mine.map((n) => (
              <li key={n.link.id}>
                <button
                  type="button"
                  className="mapper__row-btn"
                  onClick={() => props.onSelect({ kind: "link", id: n.link.id })}
                >
                  <span className="mapper__port mono" dir="ltr">
                    {shortPort(n.port)}
                  </span>
                  <span aria-hidden="true">→</span>
                  <End node={n.other} port={n.otherPort} />
                </button>
                <Swatch medium={n.link.medium} />
                <LinkStatusPill link={n.link} />
              </li>
            ))}
          </ul>
        )}
      </Panel>
    );
  }

  if (link) {
    const ends = [
      { node: byId.get(link.a.device_id), port: link.a.port },
      { node: byId.get(link.b.device_id), port: link.b.port },
    ];
    return (
      <Panel className="mapper__details" title={t("details")} actions={close}>
        <LinkStatusPill link={link} />
        {link.reason && <p className="mapper__muted">{t(`r_${link.reason}`)}</p>}
        <ul className="mapper__ends">
          {ends.map(({ node: n, port }) => (
            <li key={`${n?.id}:${port}`}>
              <button
                type="button"
                className="mapper__row-btn"
                onClick={() => n && props.onSelect({ kind: "node", id: n.id })}
              >
                <End node={n} port={port} />
              </button>
            </li>
          ))}
        </ul>
        <dl className="mapper__facts">
          <dt>{t("medium")}</dt>
          <dd>
            <span className="mapper__medium">
              <Swatch medium={link.medium} />
              {t(`m_${link.medium}`)}
            </span>
          </dd>
          <dt>{t("speed")}</dt>
          <dd className="num">{speed(link.speed_mbps, t)}</dd>
        </dl>
      </Panel>
    );
  }

  return (
    <Panel className="mapper__details" title={t("details")}>
      <p className="mapper__muted">{t("pick")}</p>
    </Panel>
  );
}
