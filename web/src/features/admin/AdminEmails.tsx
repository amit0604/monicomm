import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Button, Panel, StatusPill } from "../../components/ui";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/en";
import "./admin.css";

// Mirrors api/app/modules/admin/emails.py.
interface EmailsView {
  env: string[];
  saved: string[];
}

const URL = "/api/v1/admin/emails";

export function AdminEmails() {
  const { t } = useI18n();
  const [view, setView] = useState<EmailsView | null>(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; key: MessageKey } | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    fetch(URL, { signal: abort.signal })
      .then(async (res) => {
        if (res.ok) setView((await res.json()) as EmailsView);
        // No access: the panel above already says to sign in.
        else if (res.status !== 401 && res.status !== 403) throw new Error();
      })
      .catch(() => {
        if (!abort.signal.aborted) setNotice({ ok: false, key: "admin.error.failed" });
      });
    return () => abort.abort();
  }, []);

  async function save(emails: string[], done: MessageKey): Promise<boolean> {
    setBusy(true);
    setNotice(null);
    let key: MessageKey = "admin.error.failed";
    let ok = false;
    try {
      const res = await fetch(URL, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ emails }),
      });
      if (res.ok) {
        setView((await res.json()) as EmailsView);
        [ok, key] = [true, done];
      } else if (res.status === 422) key = "admin.emails.invalid";
      else if (res.status === 401 || res.status === 403) key = "admin.error.access";
    } catch {
      // Server unreachable.
    }
    setNotice({ ok, key });
    setBusy(false);
    return ok;
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    if (view && (await save([...view.saved, email.trim()], "admin.emails.added"))) setEmail("");
  }

  function remove(target: string) {
    if (!view || !window.confirm(t("admin.emails.remove_confirm", { email: target }))) return;
    void save(
      view.saved.filter((x) => x !== target),
      "admin.emails.removed",
    );
  }

  if (!view && !notice) return null;
  return (
    <div className="admin">
      <Panel title={t("admin.emails.title")}>
        <div className="admin__form">
          <p className="muted">{t("admin.emails.note")}</p>
          {view && (
            <>
              <ul className="admin__list">
                {view.env.map((x) => (
                  <li key={`env-${x}`}>
                    <bdi>{x}</bdi>
                    <span className="muted">{t("admin.emails.env")}</span>
                  </li>
                ))}
                {view.saved.map((x) => (
                  <li key={x}>
                    <bdi>{x}</bdi>
                    <Button
                      variant="ghost"
                      iconOnly
                      disabled={busy}
                      aria-label={t("admin.emails.remove", { email: x })}
                      onClick={() => remove(x)}
                    >
                      <Trash2 size={16} aria-hidden="true" />
                    </Button>
                  </li>
                ))}
              </ul>
              <form className="admin__form" onSubmit={(e) => void add(e)}>
                <label className="field">
                  {t("admin.emails.label")}
                  <input
                    className="admin__control"
                    type="email"
                    dir="ltr"
                    required
                    maxLength={254}
                    disabled={busy}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </label>
                <div className="admin__actions">
                  <Button variant="primary" type="submit" disabled={busy}>
                    <Plus size={16} aria-hidden="true" />
                    {t("admin.emails.add")}
                  </Button>
                </div>
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
