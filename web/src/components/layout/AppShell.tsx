import { useState } from "react";
import type { ReactNode } from "react";
import type { Theme } from "../../lib/theme";
import type { PageId } from "../../modules";
import { SideNav } from "./SideNav";
import { TopBar } from "./TopBar";
import "./layout.css";

export function AppShell({
  active,
  title,
  theme,
  onNavigate,
  onToggleTheme,
  children,
}: {
  active: PageId;
  title: string;
  theme: Theme;
  onNavigate: (id: PageId) => void;
  onToggleTheme: () => void;
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className={collapsed ? "shell shell--collapsed" : "shell"}>
      <SideNav
        active={active}
        collapsed={collapsed}
        onNavigate={onNavigate}
        onToggle={() => setCollapsed((c) => !c)}
      />
      <div className="shell__main">
        <TopBar title={title} theme={theme} onToggleTheme={onToggleTheme} />
        <main className="shell__content">{children}</main>
      </div>
    </div>
  );
}
