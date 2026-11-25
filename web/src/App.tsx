import { useEffect, useState } from "react";
import { Languages, Moon, Sun } from "lucide-react";
import { MODULES, type ModuleId } from "./modules";
import { StatusPill } from "./components/ui/StatusPill";
import { LiveChat } from "./features/chat/LiveChat";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { TextProvider, useText } from "./text";

type Theme = "light" | "dark";

function initialTheme(): Theme {
  if (typeof window.matchMedia !== "function") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function LanguageButton() {
  const { t, toggle } = useText();
  return (
    <button type="button" className="button" onClick={toggle}>
      <Languages size={16} aria-hidden="true" />
      {t("language")}
    </button>
  );
}

export default function App() {
  const [active, setActive] = useState<ModuleId>("dashboard");
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const current = MODULES.find((m) => m.id === active)!;

  return (
    <TextProvider>
      <div className="shell">
        <nav className="nav" aria-label="Modules">
          <div className="nav__brand">Monicomm</div>
          {MODULES.map((m) => (
            <button
              key={m.id}
              type="button"
              className="nav__item"
              aria-current={m.id === active ? "page" : undefined}
              onClick={() => setActive(m.id)}
            >
              <span className="nav__dot" style={{ background: `var(--accent-${m.id})` }} />
              {m.name}
            </button>
          ))}
        </nav>
        <div>
          <header className="topbar">
            <h1>{current.name}</h1>
            <span className="topbar__actions">
              <LanguageButton />
              <button
                type="button"
                className="button"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              >
                {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
              </button>
            </span>
          </header>
          <main className="content">
            {active === "dashboard" ? (
              <DashboardPage />
            ) : active === "chat" ? (
              <LiveChat />
            ) : (
              <section className="panel">
                <StatusPill status="info" label="Coming soon" />
              </section>
            )}
          </main>
        </div>
      </div>
    </TextProvider>
  );
}
