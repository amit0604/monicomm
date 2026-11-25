import { PlugZap, Save, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Button, ErrorState, Panel, Skeleton, StatusPill } from "../../components/ui";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/en";
import { AdminError, llmApi, type LLMForm, type LLMView } from "./api";
import "./admin.css";

const KEY_LABEL: Record<LLMView["key_source"], MessageKey> = {
  none: "admin.key_none",
  env: "admin.key_env",
  saved: "admin.key_saved",
};

interface Notice {
  ok: boolean;
  key: MessageKey;
}

const errorKey = (e: unknown): MessageKey =>
  e instanceof AdminError ? `admin.error.${e.code}` : "admin.error.failed";

export function AdminPage() {
  const { t } = useI18n();
  const [view, setView] = useState<LLMView | null>(null);
  const [loadError, setLoadError] = useState<MessageKey | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState<"test" | "save" | "reset" | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  const load = useCallback(() => {
    setLoadError(null);
    llmApi.read().then(setView, (e: unknown) => setLoadError(errorKey(e)));
  }, []);
  useEffect(load, [load]);

  if (loadError)
    return <ErrorState message={t(loadError)} onRetry={load} retryLabel={t("dash.retry")} />;
  if (!view) return <Skeleton />;

  const gemini = view.provider === "gemini";
  const form: LLMForm = {
    provider: view.provider,
    base_url: view.base_url,
    model: view.model,
    gemini_model: view.gemini_model,
    api_key: apiKey.trim() || null,
  };
  const change = (patch: Partial<LLMView>) => {
    setView({ ...view, ...patch });
    setNotice(null);
  };

  async function run(name: "test" | "save" | "reset", work: () => Promise<Notice>) {
    setBusy(name);
    setNotice(null);
    try {
      setNotice(await work());
    } catch (e) {
      setNotice({ ok: false, key: errorKey(e) });
    }
    setBusy(null);
  }

  const test = () =>
    run("test", async () => {
      const { ok, error } = await llmApi.test(form);
      return ok
        ? { ok, key: "admin.test_ok" }
        : { ok, key: `admin.error.${error ?? "unavailable"}` };
    });

  function save(e: FormEvent) {
    e.preventDefault();
    void run("save", async () => {
      setView(await llmApi.save(form));
      setApiKey("");
      return { ok: true, key: "admin.saved" };
    });
  }

  function reset() {
    if (!window.confirm(t("admin.reset_confirm"))) return;
    void run("reset", async () => {
      setView(await llmApi.reset());
      setApiKey("");
      return { ok: true, key: "admin.was_reset" };
    });
  }

  return (
    <div className="admin">
      <Panel
        title={t("admin.title")}
        actions={
          <StatusPill
            status={view.key_source === "none" ? "warning" : "ok"}
            label={t(KEY_LABEL[view.key_source])}
          />
        }
      >
        <form className="admin__form" onSubmit={save}>
          <p className="muted">{t("admin.dev")}</p>
          {import.meta.env.VITE_CHAT_BACKEND !== "api" && <p>{t("admin.mock")}</p>}
          {/* Locked while a request runs, so what is on screen is what was sent. */}
          <fieldset className="admin__fields" disabled={busy !== null}>
            <label className="field">
              {t("admin.provider")}
              <select
                className="admin__control"
                value={view.provider}
                onChange={(e) => change({ provider: e.target.value as LLMView["provider"] })}
              >
                <option value="gemini">{t("admin.gemini")}</option>
                <option value="ollama">{t("admin.ollama")}</option>
              </select>
            </label>
            {gemini ? (
              <label className="field">
                {t("admin.key")}
                <input
                  className="admin__control"
                  type="password"
                  dir="ltr"
                  autoComplete="new-password"
                  spellCheck={false}
                  maxLength={500}
                  required={view.key_source === "none"}
                  placeholder={view.key_source === "none" ? "" : t("admin.key_keep")}
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    setNotice(null);
                  }}
                />
              </label>
            ) : (
              <label className="field">
                {t("admin.url")}
                <input
                  className="admin__control"
                  dir="ltr"
                  required
                  maxLength={300}
                  value={view.base_url}
                  onChange={(e) => change({ base_url: e.target.value })}
                />
              </label>
            )}
            <label className="field">
              {t("admin.model")}
              <input
                className="admin__control"
                dir="ltr"
                required
                maxLength={100}
                value={gemini ? view.gemini_model : view.model}
                onChange={(e) =>
                  change(gemini ? { gemini_model: e.target.value } : { model: e.target.value })
                }
              />
            </label>
            <div className="admin__actions">
              <Button variant="primary" type="submit">
                <Save size={16} aria-hidden="true" />
                {t("admin.save")}
              </Button>
              <Button onClick={() => void test()}>
                <PlugZap size={16} aria-hidden="true" />
                {t(busy === "test" ? "admin.testing" : "admin.test")}
              </Button>
              {view.saved && (
                <Button variant="danger" onClick={reset}>
                  <Trash2 size={16} aria-hidden="true" />
                  {t("admin.reset")}
                </Button>
              )}
            </div>
          </fieldset>
          {notice && (
            <div role={notice.ok ? "status" : "alert"}>
              <StatusPill status={notice.ok ? "ok" : "critical"} label={t(notice.key)} />
            </div>
          )}
        </form>
      </Panel>
    </div>
  );
}
