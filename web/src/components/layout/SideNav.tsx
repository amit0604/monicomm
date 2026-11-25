import type { CSSProperties } from "react";
import { PanelLeftClose, PanelLeftOpen, Radar, Settings } from "lucide-react";
import { useI18n } from "../../i18n";
import { useSession } from "../../features/auth/session";
import type { PageId } from "../../modules";
import { MODULE_LIST } from "./modules";

export function SideNav({
  active,
  collapsed,
  onNavigate,
  onToggle,
}: {
  active: PageId;
  collapsed: boolean;
  onNavigate: (id: PageId) => void;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  const isAdmin = useSession()?.role === "admin";
  const ToggleIcon = collapsed ? PanelLeftOpen : PanelLeftClose;

  return (
    <aside className={collapsed ? "sidenav sidenav--collapsed" : "sidenav"}>
      <nav className="sidenav__nav" aria-label="Modules">
        <div className="sidenav__brand">
          <span className="sidenav__logo" aria-hidden="true">
            <Radar size={20} />
          </span>
          {!collapsed && <span className="sidenav__name">{t("app.name")}</span>}
        </div>

        <ul className="sidenav__list">
          {MODULE_LIST.map(({ id, label, icon: Icon }) => (
            <li key={id}>
              <button
                type="button"
                className={id === active ? "sidenav__item sidenav__item--active" : "sidenav__item"}
                aria-current={id === active ? "page" : undefined}
                aria-label={collapsed ? t(label) : undefined}
                title={collapsed ? t(label) : undefined}
                onClick={() => onNavigate(id)}
                style={{ "--nav-accent": `var(--accent-${id})` } as CSSProperties}
              >
                <span className="sidenav__icon" aria-hidden="true">
                  <Icon size={20} />
                </span>
                {!collapsed && t(label)}
              </button>
            </li>
          ))}
          {isAdmin && (
            <li>
              <button
                type="button"
                className={
                  active === "admin" ? "sidenav__item sidenav__item--active" : "sidenav__item"
                }
                aria-current={active === "admin" ? "page" : undefined}
                aria-label={collapsed ? t("nav.admin") : undefined}
                title={collapsed ? t("nav.admin") : undefined}
                onClick={() => onNavigate("admin")}
                style={{ "--nav-accent": "var(--border)" } as CSSProperties}
              >
                <span className="sidenav__icon" aria-hidden="true">
                  <Settings size={20} />
                </span>
                {!collapsed && t("nav.admin")}
              </button>
            </li>
          )}
        </ul>
      </nav>

      <button
        type="button"
        className="sidenav__toggle"
        onClick={onToggle}
        aria-label={collapsed ? t("nav.expand") : t("nav.collapse")}
      >
        <ToggleIcon size={20} aria-hidden="true" className="flip-rtl" />
      </button>
    </aside>
  );
}
