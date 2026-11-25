import { LogOut } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button, ErrorState } from "../../components/ui";
import { useI18n } from "../../i18n";
import { LoginPage } from "./LoginPage";
import { SessionContext, type User } from "./session";
import "./auth.css";

const CHECK_MS = 60_000;

type State =
  | { is: "checking" | "unreachable" | "off" | "signed_out" }
  | { is: "signed_in"; user: User };

async function check(): Promise<State> {
  try {
    const res = await fetch("/api/v1/auth/me");
    if (res.ok) return { is: "signed_in", user: (await res.json()) as User };
    if (res.status === 401) return { is: "signed_out" };
    if (res.status === 404) return { is: "off" }; // MONICOMM_AUTH_PROVIDER=none
  } catch {
    // Server unreachable.
  }
  return { is: "unreachable" };
}

/** Shows the app only to a signed-in user, or to all when the api has login off. The api enforces this. */
export function AuthGate({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const [state, setState] = useState<State>({ is: "checking" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    const run = async () => {
      const next = await check();
      // Once the app is open, a server that is briefly away must not close it.
      if (active)
        setState((s) =>
          next.is === "unreachable" && (s.is === "signed_in" || s.is === "off") ? s : next,
        );
    };
    void run();
    const timer = setInterval(() => void run(), CHECK_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [attempt]);

  async function leave() {
    const res = await fetch("/api/v1/auth/session", { method: "DELETE" }).catch(() => null);
    if (res?.ok || res?.status === 401) setState({ is: "signed_out" });
  }

  switch (state.is) {
    case "checking":
      return null;
    case "unreachable":
      return (
        <ErrorState
          message={t("auth.unreachable")}
          onRetry={() => setAttempt((n) => n + 1)}
          retryLabel={t("dash.retry")}
        />
      );
    case "off":
      return children;
    case "signed_out":
      return <LoginPage onUser={(user) => setState({ is: "signed_in", user })} />;
    case "signed_in":
      return (
        <SessionContext value={state.user}>
          {children}
          <div className="login__user">
            <bdi>{state.user.name}</bdi>
            <Button size="sm" onClick={() => void leave()}>
              <LogOut size={16} aria-hidden="true" />
              {t("auth.sign_out")}
            </Button>
          </div>
        </SessionContext>
      );
  }
}
