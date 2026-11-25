import type { ReactNode } from "react";
import { StatusPill, Tag } from "../../components/ui";
import type { Status } from "../../components/ui";
import { useI18n } from "../../i18n";
import type { ItemStatus, LinkLoad, Report, Reroute, Risk } from "./api";

export const RISK_STATUS: Record<Risk, Status> = { low: "ok", medium: "warning", high: "critical" };

export function RiskPill({ risk }: { risk: Risk }) {
  const { t } = useI18n();
  return <StatusPill status={RISK_STATUS[risk]} label={t(`analyzer.risk.${risk}`)} />;
}

function UtilPill({ pct }: { pct: number | null }) {
  const { t } = useI18n();
  if (pct === null) return <StatusPill status="neutral" label={t("analyzer.status.neutral")} />;
  // same rule as api/app/core/graph.py util_status (default MONICOMM_LINK_UTIL_WARN=0.8)
  const status: Status = pct >= 100 ? "critical" : pct >= 80 ? "warning" : "ok";
  return <StatusPill status={status} label={`${pct.toFixed(1)}%`} />;
}

const hour = (h: number) => `${String(h % 24).padStart(2, "0")}:00`;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="impact__section">
      <h3 className="impact__heading">{title}</h3>
      {children}
    </section>
  );
}

export function ImpactReport({ report }: { report: Report }) {
  const { t, absolute } = useI18n();
  const none = <p className="muted">{t("analyzer.none")}</p>;
  const w = report.maintenance_window;
  const rows = report.reroutes.flatMap((r): { r: Reroute; a: LinkLoad | null; first: boolean }[] =>
    r.after.length
      ? r.after.map((a, i) => ({ r, a, first: i === 0 }))
      : [{ r, a: null, first: true }],
  );

  return (
    <article className="impact" aria-label={report.title}>
      <header className="impact__header">
        <h2 className="impact__title">{report.title}</h2>
        <div className="impact__meta">
          <RiskPill risk={report.risk} />
          {report.source === "demo" && <Tag>{t("analyzer.demo")}</Tag>}
          <time className="muted num" dateTime={report.created_at}>
            {absolute(report.created_at)}
          </time>
        </div>
      </header>
      <p>{report.summary}</p>

      <Section title={t("analyzer.affected")}>
        {report.affected.length ? (
          <ul className="impact__list">
            {report.affected.map((a) => (
              <li key={`${a.kind}:${a.id}`} className="impact__item">
                <StatusPill
                  status={a.status}
                  label={t(`analyzer.status.${a.status satisfies ItemStatus}`)}
                />
                <span className="mono">{a.label}</span>
                <span className="muted">{a.detail}</span>
              </li>
            ))}
          </ul>
        ) : (
          none
        )}
      </Section>

      <Section title={t("analyzer.reroutes")}>
        {rows.length ? (
          <div className="impact__table-wrap">
            <table className="impact__table">
              <thead>
                <tr>
                  <th scope="col">{t("analyzer.removed")}</th>
                  <th scope="col">{t("analyzer.via")}</th>
                  <th scope="col">{t("analyzer.link")}</th>
                  <th scope="col">{t("analyzer.before")}</th>
                  <th scope="col">{t("analyzer.after")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ r, a, first }) => (
                  <tr key={`${r.link}:${a?.link ?? "none"}`}>
                    <td className="mono">{first ? r.link : ""}</td>
                    <td className="mono">{first ? r.via.join(" → ") : ""}</td>
                    {a ? (
                      <>
                        <td className="mono">{a.label}</td>
                        <td className="num">
                          {a.util_before === null
                            ? t("analyzer.status.neutral")
                            : `${a.util_before.toFixed(1)}%`}
                        </td>
                        <td className="num">
                          <UtilPill pct={a.util_after} />
                        </td>
                      </>
                    ) : (
                      <td colSpan={3}>
                        <StatusPill status="critical" label={t("analyzer.noPath")} />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          none
        )}
      </Section>

      <Section title={t("analyzer.spofs")}>
        {report.new_spofs.length ? (
          <ul className="impact__list">
            {report.new_spofs.map((s) => (
              <li key={s.id} className="impact__item">
                <StatusPill status="warning" label={t("analyzer.status.warning")} />
                <span className="mono">{s.label}</span>
              </li>
            ))}
          </ul>
        ) : (
          none
        )}
      </Section>

      <Section title={t("analyzer.window")}>
        <p className="num">
          {w
            ? t("analyzer.windowValue", {
                start: hour(w.start_hour),
                end: hour(w.end_hour),
                avg: w.avg_util_pct.toFixed(1),
              })
            : t("analyzer.noWindow")}
        </p>
      </Section>

      <Section title={t("analyzer.rollback")}>
        <pre className="mono impact__code" dir="ltr">
          {report.rollback}
        </pre>
      </Section>

      {report.warnings.length > 0 && (
        <Section title={t("analyzer.warnings")}>
          <ul className="impact__list">
            {report.warnings.map((text) => (
              <li key={text} className="impact__item">
                <StatusPill status="warning" label={t("analyzer.status.warning")} />
                {text}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title={t("analyzer.unknowns")}>
        {report.unknowns.length ? (
          <ul className="impact__pills">
            {report.unknowns.map((text) => (
              <li key={text}>
                <StatusPill status="neutral" label={text} />
              </li>
            ))}
          </ul>
        ) : (
          none
        )}
      </Section>

      <Section title={t("analyzer.dataUsed")}>
        <ul className="impact__plain muted">
          {report.data_used.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      </Section>
    </article>
  );
}
