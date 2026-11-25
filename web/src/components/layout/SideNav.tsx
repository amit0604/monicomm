import { PanelLeftClose, PanelLeftOpen, Radar } from 'lucide-react';
import { useI18n } from '../../i18n';
import type { ModuleId } from '../../lib/useHashRoute';
import { MODULE_LIST } from './modules';

export function SideNav({
  active,
  collapsed,
  onToggle,
}: {
  active: ModuleId;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  const ToggleIcon = collapsed ? PanelLeftOpen : PanelLeftClose;

  return (
    <nav className={collapsed ? 'sidenav sidenav--collapsed' : 'sidenav'} aria-label="Modules">
      <div className="sidenav__brand">
        <span className="sidenav__logo" aria-hidden="true">
          <Radar size={20} />
        </span>
        {!collapsed && <span className="sidenav__name">{t('app.name')}</span>}
      </div>

      <ul className="sidenav__list">
        {MODULE_LIST.map(({ id, label, icon: Icon, accentVar }) => (
          <li key={id}>
            <a
              href={`#/${id}`}
              className={id === active ? 'sidenav__item sidenav__item--active' : 'sidenav__item'}
              aria-current={id === active ? 'page' : undefined}
              title={collapsed ? t(label) : undefined}
              style={{ '--accent': `var(${accentVar})` } as React.CSSProperties}
            >
              <span className="sidenav__icon">
                <Icon size={20} aria-hidden="true" />
              </span>
              {!collapsed && <span>{t(label)}</span>}
            </a>
          </li>
        ))}
      </ul>

      <button
        type="button"
        className="sidenav__toggle"
        onClick={onToggle}
        aria-label={collapsed ? t('nav.expand') : t('nav.collapse')}
      >
        <ToggleIcon size={20} aria-hidden="true" className="flip-rtl" />
      </button>
    </nav>
  );
}
