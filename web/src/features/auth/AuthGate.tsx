import { LogOut } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "../../components/ui";
import { useI18n } from "../../i18n";
import { LoginPage, type User } from "./LoginPage";

const CHECK_MS = 60_000;

/** Shows the app only to a signed-in user. The api enforces this too; the gate is just the way in. */
export default function AuthGate({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch("/api/v1/auth/me");
        if (res.ok) setUser((await res.json()) as User);
        else if (res.status === 401) setUser(null);
      } catch {
        // Server unreachable: keep what is on screen, its own views report the problem.
      }
      setChecked(true);
    };
    void check();
    const timer = setInterval(() => void check(), CHECK_MS);
    return () => clearInterval(timer);
  }, []);

  async function leave() {
    const res = await fetch("/api/v1/auth/session", { method: "DELETE" }).catch(() => null);
    if (res?.ok || res?.status === 401) setUser(null);
  }

  if (!checked) return null;
  if (!user) return <LoginPage onUser={setUser} />;
  return (
    <>
      {children}
      <div className="login__user">
        <bdi>{user.name}</bdi>
        <Button size="sm" onClick={() => void leave()}>
          <LogOut size={16} aria-hidden="true" />
          {t("auth.sign_out")}
        </Button>
      </div>
    </>
  );
}
