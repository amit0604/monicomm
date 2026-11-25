import { LogIn, TriangleAlert } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button, Panel } from "../../components/ui";
import type { MessageKey } from "../../i18n/en";
import { he } from "../../i18n/he";
import { useTheme } from "../../lib/theme";
import type { User } from "./session";
import "./auth.css";

// The login page is in Hebrew only, whatever language the app is in.
const t = (key: MessageKey) => he[key];

export function LoginPage({ onUser }: { onUser: (user: User) => void }) {
  useTheme(); // the app shell, which normally applies it, is not on screen yet
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    let key: MessageKey = "auth.failed";
    try {
      const res = await fetch("/api/v1/auth/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, password }),
      });
      if (res.ok) return onUser((await res.json()) as User);
      if (res.status === 401 || res.status === 422) key = "auth.wrong";
      if (res.status === 429) key = "auth.too_many";
    } catch {
      // Server unreachable.
    }
    setPassword("");
    setError(key);
    setBusy(false);
  }

  return (
    <main className="login" dir="rtl" lang="he">
      <Panel className="login__panel">
        <h1 className="login__title">Monicomm</h1>
        {error && (
          <p className="login__error" role="alert">
            <TriangleAlert size={16} aria-hidden="true" />
            {t(error)}
          </p>
        )}
        <form className="login__form" onSubmit={(e) => void submit(e)}>
          <label>
            {t("auth.login")}
            <input
              className="login__field"
              dir="ltr"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              maxLength={64}
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            {t("auth.password")}
            <input
              className="login__field"
              dir="ltr"
              type="password"
              autoComplete="current-password"
              maxLength={200}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <Button variant="primary" type="submit" disabled={busy}>
            <LogIn size={16} aria-hidden="true" />
            {t("auth.sign_in")}
          </Button>
        </form>
      </Panel>
    </main>
  );
}
