import { PlugZap, Save, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Button, ErrorState, Panel, Skeleton, StatusPill } from "../../components/ui";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/en";
import { authApi, type AuthSection, type AuthValue, type AuthView } from "./api";
import { errorKey, NoticeLine, useAction } from "./useAction";

export interface FieldSpec {
  name: string;
  label: MessageKey;
  kind?: "text" | "checkbox" | "role";
  required?: boolean;
  placeholder?: string;
}

const ROLES: { value: string; label: MessageKey }[] = [
  { value: "viewer", label: "admin.users.role_viewer" },
  { value: "technician", label: "admin.users.role_technician" },
  { value: "none", label: "admin.auth.role_none" },
];

const TEST_ERRORS = new Set([
  "incomplete",
  "external_url",
  "unreachable",
  "tls_failed",
  "bind_failed",
  "base_not_found",
  "user_not_found",
  "bad_discovery",
  "issuer_mismatch",
]);

/** LDAP or SSO settings on the Admin page: edit, save, test the connection, delete. */
export function AuthMethodPanel({
  section,
  title,
  intro,
  fields,
  secret,
  testUser,
}: {
  section: AuthSection;
  title: MessageKey;
  intro: MessageKey;
  fields: FieldSpec[];
  /** The write-only secret field (shown empty; empty keeps the current one). */
  secret: { name: string; label: MessageKey };
  /** LDAP only: an optional user to look up during the test. */
  testUser?: MessageKey;
}) {
  const { t } = useI18n();
  const api = authApi(section);
  const [view, setView] = useState<AuthView | null>(null);
  const [values, setValues] = useState<Record<string, AuthValue>>({});
  const [loadError, setLoadError] = useState<MessageKey | null>(null);
  const [secretValue, setSecretValue] = useState("");
  const [lookup, setLookup] = useState("");
  const { busy, notice, setNotice, run } = useAction<"test" | "save" | "reset">();

  const show = useCallback(
    (next: AuthView) => {
      setView(next);
      setValues(Object.fromEntries(fields.map((f) => [f.name, next[f.name] ?? ""])));
      setSecretValue("");
    },
    [fields],
  );
  const load = useCallback(() => {
    setLoadError(null);
    authApi(section)
      .read()
      .then(show, (e: unknown) => setLoadError(errorKey(e)));
  }, [section, show]);
  useEffect(load, [load]);

  if (loadError)
    return <ErrorState message={t(loadError)} onRetry={load} retryLabel={t("dash.retry")} />;
  if (!view) return <Skeleton />;

  const form = { ...values, [secret.name]: secretValue || null };
  const set = (name: string, value: AuthValue) => {
    setValues({ ...values, [name]: value });
    setNotice(null);
  };

  const test = () =>
    run("test", async () => {
      const result = await api.test(testUser ? { ...form, username: lookup.trim() } : form);
      if (!result.ok) {
        const code = result.error && TEST_ERRORS.has(result.error) ? result.error : "failed";
        return { ok: false, key: `admin.auth.test.${code}` as MessageKey };
      }
      if (result.user)
        return {
          ok: true,
          key: "admin.ldap.found",
          vars: { dn: result.user.dn, role: result.user.role },
        };
      return { ok: true, key: "admin.auth.test_ok" };
    });

  function save(e: FormEvent) {
    e.preventDefault();
    void run("save", async () => {
      show(await api.save(form));
      return { ok: true, key: "admin.auth.saved" };
    });
  }

  function reset() {
    if (!window.confirm(t("admin.auth.reset_confirm", { name: t(title) }))) return;
    void run("reset", async () => {
      show(await api.reset());
      return { ok: true, key: "admin.auth.was_reset" };
    });
  }

  return (
    <Panel
      title={t(title)}
      actions={
        <StatusPill
          status={view.enabled ? "ok" : "neutral"}
          label={t(view.enabled ? "admin.auth.on" : "admin.auth.off")}
        />
      }
    >
      <form className="admin__form" onSubmit={save} aria-label={t(title)}>
        <p className="muted">{t(intro)}</p>
        {view.callback_url && (
          <p className="admin__note">
            {t("admin.sso.callback")} <bdi dir="ltr">{view.callback_url}</bdi>
          </p>
        )}
        <fieldset className="admin__fields" disabled={busy !== null}>
          {fields.map((f) =>
            f.kind === "checkbox" ? (
              <label key={f.name} className="admin__check">
                <input
                  type="checkbox"
                  checked={values[f.name] === true}
                  onChange={(e) => set(f.name, e.target.checked)}
                />
                {t(f.label)}
              </label>
            ) : f.kind === "role" ? (
              <label key={f.name} className="field">
                {t(f.label)}
                <select
                  className="admin__control"
                  value={String(values[f.name] ?? "viewer")}
                  onChange={(e) => set(f.name, e.target.value)}
                >
                  {ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {t(r.label)}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <label key={f.name} className="field">
                {t(f.label)}
                <input
                  className="admin__control"
                  dir="ltr"
                  spellCheck={false}
                  maxLength={500}
                  required={f.required}
                  placeholder={f.placeholder}
                  value={String(values[f.name] ?? "")}
                  onChange={(e) => set(f.name, e.target.value)}
                />
              </label>
            ),
          )}
          <label className="field">
            {t(secret.label)}
            <input
              className="admin__control"
              type="password"
              dir="ltr"
              autoComplete="new-password"
              spellCheck={false}
              maxLength={500}
              placeholder={view.secret_source === "none" ? "" : t("admin.auth.secret_keep")}
              value={secretValue}
              onChange={(e) => {
                setSecretValue(e.target.value);
                setNotice(null);
              }}
            />
          </label>
          {testUser && (
            <label className="field">
              {t(testUser)}
              <input
                className="admin__control"
                dir="ltr"
                autoComplete="off"
                spellCheck={false}
                maxLength={128}
                value={lookup}
                onChange={(e) => setLookup(e.target.value)}
              />
            </label>
          )}
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
        <NoticeLine notice={notice} />
      </form>
    </Panel>
  );
}
