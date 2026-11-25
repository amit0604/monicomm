import type { CSSProperties } from "react";
import { PanelLeftClose, PanelLeftOpen, Radar } from "lucide-react";
import { useI18n } from "../../i18n";
import type { ModuleId } from "../../modules";
import { MODULE_LIST } from "./modules";

export function SideNav({
  active,
  collapsed,
  onNavigate,
  onToggle,
}: {
  active: ModuleId;
  collapsed: boolean;
  onNavigate: (id: ModuleId) => void;
  onToggle: () => void;
}) {
  const { t } = useI18n();
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
