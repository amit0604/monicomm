import { ArrowLeftRight, Bell, Moon, Sun, UserRound } from "lucide-react";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/en";
import { Button } from "../ui";
import type { Theme } from "../../lib/theme";

const RANGES: MessageKey[] = ["time.15m", "time.1h", "time.6h", "time.24h", "time.7d"];

export function TopBar({
  title,
  theme,
  onToggleTheme,
}: {
  title: string;
  theme: Theme;
  onToggleTheme: () => void;
}) {
  const { t, dir, setDir } = useI18n();
  const themeLabel = t(theme === "dark" ? "topbar.themeToLight" : "topbar.themeToDark");

  return (
    <header className="topbar">
      <h1 className="topbar__title">{title}</h1>
      <div className="topbar__actions">
        <label className="visually-hidden" htmlFor="time-range">
          {t("topbar.timeRange")}
        </label>
        <select id="time-range" className="topbar__select" defaultValue="time.24h">
          {RANGES.map((key) => (
            <option key={key} value={key}>
              {t(key)}
            </option>
          ))}
        </select>
        <Button
          variant="ghost"
          iconOnly
          aria-label={t("topbar.direction")}
          title={t("topbar.direction")}
          onClick={() => setDir(dir === "ltr" ? "rtl" : "ltr")}
        >
          <ArrowLeftRight size={16} aria-hidden="true" />
          <span className="topbar__dir">{dir.toUpperCase()}</span>
        </Button>
        <Button
          variant="ghost"
          iconOnly
          aria-label={themeLabel}
          title={themeLabel}
          onClick={onToggleTheme}
        >
          {theme === "dark" ? (
            <Sun size={16} aria-hidden="true" />
          ) : (
            <Moon size={16} aria-hidden="true" />
          )}
        </Button>
        <Button variant="ghost" iconOnly aria-label={t("topbar.alerts")} title={t("topbar.alerts")}>
          <Bell size={16} aria-hidden="true" />
        </Button>
        <span className="topbar__user" title={t("topbar.user")}>
          <UserRound size={16} aria-hidden="true" />
        </span>
      </div>
    </header>
  );
}
