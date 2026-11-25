import { LogIn, TriangleAlert } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Button, Panel } from "../../components/ui";
import type { MessageKey } from "../../i18n/en";
import { he } from "../../i18n/he";
import { useTheme } from "../../lib/theme";
import type { FirebaseSettings, SignIn } from "./firebase";
import "./auth.css";

export interface User {
  name: string;
  role: string;
}

class LoginError extends Error {
  constructor(readonly key: MessageKey) {
    super(key);
  }
}

const WRONG = ["invalid-credential", "wrong-password", "user-not-found", "invalid-email"];

/** null = the user closed the Google window, which is not an error. */
function explain(error: unknown): MessageKey | null {
  if (error instanceof LoginError) return error.key;
  const code = String((error as { code?: unknown } | null)?.code ?? "").replace("auth/", "");
  if (code === "popup-closed-by-user" || code === "cancelled-popup-request") return null;
  if (WRONG.includes(code)) return "auth.wrong";
  if (code === "too-many-requests") return "auth.too_many";
  if (code === "popup-blocked") return "auth.popup_blocked";
  if (code === "unauthorized-domain" || code === "operation-not-allowed") return "auth.setup";
  return "auth.failed";
}

async function openSession(idToken: string): Promise<User> {
  const res = await fetch("/api/v1/auth/session", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ id_token: idToken }),
  });
  if (res.ok) return (await res.json()) as User;
  throw new LoginError(res.status === 403 ? "auth.not_allowed" : "auth.failed");
}

// The login page is in Hebrew only, whatever language the app is in.
const t = (key: MessageKey) => he[key];

export function LoginPage({ onUser }: { onUser: (user: User) => void }) {
  useTheme(); // the app shell, which normally applies it, is not on screen yet
  const [settings, setSettings] = useState<FirebaseSettings | null>(null);
  const [signIn, setSignIn] = useState<SignIn | null>(null);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);

  // Loaded up front: a browser blocks the Google window unless it opens straight from the click.
  useEffect(() => {
    let active = true;
    const load = async () => {
      const res = await fetch("/api/v1/auth/config");
      if (!res.ok) throw new LoginError("auth.setup");
      const config = (await res.json()) as FirebaseSettings;
      const { createSignIn } = await import("./firebase");
      if (!active) return;
      setSettings(config);
      setSignIn(createSignIn(config));
    };
    load().catch((e: unknown) => active && setError(explain(e)));
    return () => {
      active = false;
    };
  }, []);

  async function run(getToken: () => Promise<string>) {
    setBusy(true);
    setError(null);
    try {
      onUser(await openSession(await getToken()));
    } catch (e) {
      setError(explain(e));
      setBusy(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!signIn || !settings) return;
    const name = login.trim();
    const email = name.includes("@") ? name : name === "admin" ? settings.admin_login : "";
    if (!email) return setError("auth.wrong");
    void run(() => signIn.password(email, password));
  }

  const disabled = busy || !signIn;
  return (
    <main className="login" dir="rtl" lang="he">
      <Panel className="login__panel">
        <h1 className="login__title">Monicomm</h1>
        <p className="login__note">{t("auth.dev")}</p>
        {error && (
          <p className="login__error" role="alert">
            <TriangleAlert size={16} aria-hidden="true" />
            {t(error)}
          </p>
        )}
        <form className="login__form" onSubmit={submit}>
          <label>
            {t("auth.login")}
            <input
              className="login__field"
              dir="ltr"
              autoComplete="username"
              required
              value={login}
              onChange={(e) => setLogin(e.target.value)}
            />
          </label>
          <label>
            {t("auth.password")}
            <input
              className="login__field"
              dir="ltr"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <Button variant="primary" type="submit" disabled={disabled}>
            <LogIn size={16} aria-hidden="true" />
            {t("auth.sign_in")}
          </Button>
        </form>
        <Button disabled={disabled} onClick={() => signIn && void run(signIn.google)}>
          {t("auth.google")}
        </Button>
      </Panel>
    </main>
  );
}
