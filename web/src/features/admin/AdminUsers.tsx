import { KeyRound, Plus, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Button, Panel, StatusPill } from "../../components/ui";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/en";
import type { User } from "../auth/session";
import "./admin.css";

// Mirrors api/app/modules/admin/users.py. Passwords are sent, never received.
const URL = "/api/v1/admin/users";
const ROLES: User["role"][] = ["admin", "technician", "viewer"];
const CODES = ["exists", "last_admin", "not_found", "too_many", "damaged"] as const;

async function errorOf(res: Response): Promise<MessageKey> {
  if (res.status === 401 || res.status === 403) return "admin.error.access";
  if (res.status === 422) return "admin.users.invalid";
  const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
  const code = CODES.find((c) => c === body?.detail);
  return code ? `admin.users.${code}` : "admin.error.failed";
}

export function AdminUsers() {
  const { t } = useI18n();
  const [list, setList] = useState<User[] | null>(null);
  const [name, setName] = useState("");
  const [role, setRole] = useState<User["role"]>("technician");
  const [password, setPassword] = useState("");
  /** The user whose password is being replaced; null = adding a new user. */
  const [target, setTarget] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; key: MessageKey } | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    fetch(URL, { signal: abort.signal })
      .then(async (res) => {
        if (res.ok) setList((await res.json()) as User[]);
        // No access: the panel above already says to sign in.
        else if (res.status !== 401 && res.status !== 403)
          setNotice({ ok: false, key: await errorOf(res) });
      })
      .catch(() => {
        if (!abort.signal.aborted) setNotice({ ok: false, key: "admin.error.failed" });
      });
    return () => abort.abort();
  }, []);

  async function send(method: string, path: string, body: unknown, done: MessageKey) {
    setBusy(true);
    setNotice(null);
    let next: { ok: boolean; key: MessageKey } = { ok: false, key: "admin.error.failed" };
    try {
      const res = await fetch(URL + path, {
        method,
        headers: body ? { "content-type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (res.ok) {
        if (res.status !== 204) setList((await res.json()) as User[]);
        next = { ok: true, key: done };
      } else next = { ok: false, key: await errorOf(res) };
    } catch {
      // Server unreachable.
    }
    setNotice(next);
    setBusy(false);
    return next.ok;
  }

  function cancel() {
    setTarget(null);
    setName("");
    setPassword("");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const ok =
      target === null
        ? await send("POST", "", { name, role, password }, "admin.users.added")
        : await send(
            "PUT",
            `/${encodeURIComponent(target)}/password`,
            { password },
            "admin.users.password_set",
          );
    if (ok) cancel();
  }

  function remove(user: string) {
    if (!window.confirm(t("admin.users.remove_confirm", { name: user }))) return;
    if (user === target) cancel();
    void send("DELETE", `/${encodeURIComponent(user)}`, null, "admin.users.removed");
  }

  if (!list && !notice) return null;
  return (
    <div className="admin">
      <Panel title={t("admin.users.title")}>
        <div className="admin__form">
          {list && (
            <>
              <ul className="admin__list">
                {list.map((u) => (
                  <li key={u.name}>
                    <bdi>{u.name}</bdi>
                    <span className="admin__actions">
                      <span className="muted">{t(`admin.users.role_${u.role}`)}</span>
                      <Button
                        variant="ghost"
                        iconOnly
                        disabled={busy}
                        aria-label={t("admin.users.set_password", { name: u.name })}
                        title={t("admin.users.set_password", { name: u.name })}
                        onClick={() => {
                          setTarget(u.name);
                          setPassword("");
                          setNotice(null);
                        }}
                      >
                        <KeyRound size={16} aria-hidden="true" />
                      </Button>
                      <Button
                        variant="ghost"
                        iconOnly
                        disabled={busy}
                        aria-label={t("admin.users.remove", { name: u.name })}
                        title={t("admin.users.remove", { name: u.name })}
                        onClick={() => remove(u.name)}
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </Button>
                    </span>
                  </li>
                ))}
              </ul>
              <form className="admin__form" onSubmit={(e) => void submit(e)}>
                <fieldset className="admin__fields" disabled={busy}>
                  {target === null ? (
                    <>
                      <label className="field">
                        {t("admin.users.name")}
                        <input
                          className="admin__control"
                          dir="ltr"
                          required
                          maxLength={64}
                          autoComplete="off"
                          value={name}
                          onChange={(e) => setName(e.target.value)}
                        />
                      </label>
                      <label className="field">
                        {t("admin.users.role")}
                        <select
                          className="admin__control"
                          value={role}
                          onChange={(e) => setRole(e.target.value as User["role"])}
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {t(`admin.users.role_${r}`)}
                            </option>
                          ))}
                        </select>
                      </label>
                    </>
                  ) : (
                    <p>{t("admin.users.set_password", { name: target })}</p>
                  )}
                  <label className="field">
                    {t("admin.users.password")}
                    <input
                      className="admin__control"
                      dir="ltr"
                      type="password"
                      required
                      minLength={8}
                      maxLength={200}
                      autoComplete="new-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </label>
                  <div className="admin__actions">
                    <Button variant="primary" type="submit">
                      <Plus size={16} aria-hidden="true" />
                      {t(target === null ? "admin.users.add" : "admin.save")}
                    </Button>
                    {target !== null && <Button onClick={cancel}>{t("admin.users.cancel")}</Button>}
                  </div>
                </fieldset>
              </form>
            </>
          )}
          {notice && (
            <div role={notice.ok ? "status" : "alert"}>
              <StatusPill status={notice.ok ? "ok" : "critical"} label={t(notice.key)} />
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}
