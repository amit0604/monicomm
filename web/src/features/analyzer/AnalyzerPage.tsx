import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ShieldCheck } from "lucide-react";
import { AiTag, Button, EmptyState, ErrorState, Panel, Skeleton, Tag } from "../../components/ui";
import { useI18n } from "../../i18n";
import { ApiError, createReport, getReport, getTopology, listReports, parseChange } from "./api";
import type { Change, ChangeKind, Report, ReportSummary, Topology } from "./api";
import { ImpactReport, RiskPill } from "./ImpactReport";
import "./analyzer.css";

interface Load<T> {
  data?: T;
  error?: unknown;
  loading: boolean;
}

// Loads once on mount; reload() fetches again and keeps the last data while it runs.
function useLoad<T>(load: () => Promise<T>) {
  const [state, setState] = useState<Load<T>>({ loading: true });
  const run = useCallback(async () => {
    try {
      setState({ data: await load(), loading: false });
    } catch (error) {
      setState((s) => ({ ...s, error, loading: false }));
    }
  }, [load]);
  useEffect(() => void run(), [run]);
  const reload = useCallback(() => {
    setState((s) => ({ ...s, error: undefined, loading: true }));
    void run();
  }, [run]);
  return { ...state, reload };
}

const status = (e: unknown) => (e instanceof ApiError ? e.status : 0);

export function AnalyzerPage() {
  const { t, absolute } = useI18n();
  const topo = useLoad(getTopology);
  const saved = useLoad(listReports);

  const [report, setReport] = useState<{
    data?: Report;
    error?: boolean;
    loading: boolean;
    retry?: () => void;
  }>({ loading: false });

  const show = useCallback((load: () => Promise<Report>, afterwards?: () => void) => {
    const go = () => {
      setReport({ loading: true });
      load().then(
        (data) => {
          setReport({ data, loading: false });
          afterwards?.();
        },
        () => setReport({ error: true, loading: false, retry: go }),
      );
    };
    go();
  }, []);

  let left;
  if (!topo.data && topo.loading)
    left = <Skeleton rows={5} label={t("analyzer.loadingTopology")} />;
  else if (!topo.data)
    left = (
      <ErrorState
        message={status(topo.error) === 503 ? t("analyzer.noSource") : t("analyzer.topologyFailed")}
        onRetry={topo.reload}
        retryLabel={t("analyzer.retry")}
      />
    );
  else
    left = (
      <ChangeForm
        topology={topo.data}
        busy={report.loading}
        onSimulate={(change) => show(() => createReport(change), saved.reload)}
      />
    );

  let main;
  if (report.loading) main = <Skeleton rows={6} label={t("analyzer.loadingReport")} />;
  else if (report.error)
    main = (
      <ErrorState
        message={t("analyzer.reportFailed")}
        onRetry={report.retry}
        retryLabel={t("analyzer.retry")}
      />
    );
  else if (report.data) main = <ImpactReport report={report.data} />;
  else main = <EmptyState title={t("analyzer.noReport")} body={t("analyzer.noReportBody")} />;

  return (
    <div className="analyzer">
      <Panel title={t("analyzer.plan")} className="analyzer__plan">
        {left}
      </Panel>
      <div className="analyzer__main">
        <Panel title={t("analyzer.report")}>{main}</Panel>
        <Panel title={t("analyzer.saved")}>
          <SavedList
            {...saved}
            selectedId={report.data?.id}
            onOpen={(id) => show(() => getReport(id))}
            absolute={absolute}
          />
        </Panel>
      </div>
    </div>
  );
}

function ChangeForm({
  topology,
  busy,
  onSimulate,
}: {
  topology: Topology;
  busy: boolean;
  onSimulate: (change: Change) => void;
}) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [kind, setKind] = useState<ChangeKind>("interface_down");
  const [device, setDevice] = useState("");
  const [iface, setIface] = useState("");
  const [parsing, setParsing] = useState(false);
  const [parsed, setParsed] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  const node = topology.nodes.find((n) => n.id === device);
  const needsIface = kind === "interface_down";
  const ready = node !== undefined && (!needsIface || node.interfaces.includes(iface));

  async function understand() {
    setParsing(true);
    setParseError(null);
    setParsed(false);
    try {
      const { change } = await parseChange(text.trim());
      setKind(change.kind);
      setDevice(change.device);
      setIface(change.interface ?? "");
      setParsed(true);
    } catch (e) {
      const detail = e instanceof ApiError ? e.detail : undefined;
      setParseError(
        status(e) === 503
          ? t("analyzer.modelDown")
          : detail
            ? t("analyzer.parseFailed", { reason: detail })
            : t("analyzer.parseFailedNoReason"),
      );
    } finally {
      setParsing(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (ready) onSimulate({ kind, device, interface: needsIface ? iface : null });
  }

  return (
    <form className="analyzer__form" onSubmit={submit}>
      {topology.source === "demo" && (
        <p>
          <Tag>{t("analyzer.demo")}</Tag>
        </p>
      )}
      <label className="field">
        {t("analyzer.describe")}
        <textarea
          rows={3}
          maxLength={500}
          value={text}
          placeholder={t("analyzer.describeHint")}
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      <div>
        <Button onClick={understand} disabled={parsing || !text.trim()}>
          {parsing ? t("analyzer.understanding") : t("analyzer.understand")}
        </Button>
      </div>
      {parseError && (
        <p className="analyzer__note analyzer__note--error" role="alert">
          {parseError}
        </p>
      )}
      {parsed && (
        <p className="analyzer__note" role="status">
          <AiTag /> {t("analyzer.parsed")}
        </p>
      )}

      <label className="field">
        {t("analyzer.device")}
        <select
          className="analyzer__select"
          value={device}
          onChange={(e) => {
            setDevice(e.target.value);
            setIface("");
          }}
        >
          <option value="">{t("analyzer.choose")}</option>
          {topology.nodes.map((n) => (
            <option key={n.id} value={n.id}>
              {n.id}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        {t("analyzer.action")}
        <select
          className="analyzer__select"
          value={kind}
          onChange={(e) => setKind(e.target.value as ChangeKind)}
        >
          <option value="interface_down">{t("analyzer.kind.interface_down")}</option>
          <option value="device_down">{t("analyzer.kind.device_down")}</option>
        </select>
      </label>
      {needsIface && (
        <label className="field">
          {t("analyzer.interface")}
          <select
            className="analyzer__select mono"
            value={iface}
            disabled={!node}
            onChange={(e) => setIface(e.target.value)}
          >
            <option value="">{t("analyzer.choose")}</option>
            {node?.interfaces.map((i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
          </select>
        </label>
      )}

      <div>
        <Button type="submit" variant="primary" disabled={!ready || busy}>
          {busy ? t("analyzer.simulating") : t("analyzer.simulate")}
        </Button>
      </div>
      <p className="analyzer__note muted">
        <ShieldCheck size={16} aria-hidden="true" />
        {t("analyzer.safe")}
      </p>
    </form>
  );
}

function SavedList({
  data,
  error,
  loading,
  reload,
  selectedId,
  onOpen,
  absolute,
}: Load<ReportSummary[]> & {
  reload: () => void;
  selectedId?: string;
  onOpen: (id: string) => void;
  absolute: (iso: string) => string;
}) {
  const { t } = useI18n();
  if (!data && loading) return <Skeleton rows={3} label={t("analyzer.loadingSaved")} />;
  if (!data || error)
    return (
      <ErrorState
        message={t("analyzer.savedFailed")}
        onRetry={reload}
        retryLabel={t("analyzer.retry")}
      />
    );
  if (data.length === 0)
    return <EmptyState title={t("analyzer.noSaved")} body={t("analyzer.noSavedBody")} />;
  return (
    <ul className="saved">
      {data.map((r) => (
        <li key={r.id}>
          <button
            type="button"
            className="saved__row"
            aria-current={r.id === selectedId ? "true" : undefined}
            onClick={() => onOpen(r.id)}
          >
            <RiskPill risk={r.risk} />
            <span className="saved__title">{r.title}</span>
            {r.source === "demo" && <Tag muted>{t("analyzer.demo")}</Tag>}
            <time className="muted num" dateTime={r.created_at}>
              {absolute(r.created_at)}
            </time>
          </button>
        </li>
      ))}
    </ul>
  );
}
