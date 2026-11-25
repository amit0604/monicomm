import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { MODULES, type ModuleId } from "./modules";
import { StatusPill } from "./components/ui/StatusPill";
import { ChatchupTab } from "./features/pcap/ChatchupTab";

type Theme = "light" | "dark";

function initialTheme(): Theme {
  if (typeof window.matchMedia !== "function") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const [active, setActive] = useState<ModuleId>("dashboard");
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const current = MODULES.find((m) => m.id === active)!;

  return (
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
          <button
            type="button"
            className="button"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </header>
        <main className="content">
          {active === "pcap" ? (
            <ChatchupTab theme={theme} />
          ) : (
            <section className="panel">
              <StatusPill status="info" label="Coming soon" />
            </section>
          )}
        </main>
      </div>
    </div>
  );
}
