import { useState } from "react";
import { useText } from "../../text";
import { DeviceDetail } from "./DeviceDetail";
import { Devices } from "./Devices";
import { Events } from "./Events";
import { Overview } from "./Overview";
import "./dashboard.css";

export type View =
  | { tab: "overview" }
  | { tab: "devices"; status?: string }
  | { tab: "device"; id: string }
  | { tab: "events" };

const TABS = ["overview", "devices", "events"] as const;

export function DashboardPage() {
  const { t } = useText();
  const [view, setView] = useState<View>({ tab: "overview" });
  const openDevice = (id: string) => setView({ tab: "device", id });
  const active = view.tab === "device" ? "devices" : view.tab;

  return (
    <div className="dash">
      <nav className="tabs" aria-label={t("sections")}>
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            className="tabs__item"
            aria-current={tab === active ? "page" : undefined}
            onClick={() => setView({ tab })}
          >
            {t(tab)}
          </button>
        ))}
      </nav>
      {view.tab === "overview" && <Overview onView={setView} onDevice={openDevice} />}
      {view.tab === "devices" && (
        <Devices key={view.status ?? ""} initialStatus={view.status} onDevice={openDevice} />
      )}
      {view.tab === "device" && (
        <DeviceDetail key={view.id} id={view.id} onBack={() => setView({ tab: "devices" })} />
      )}
      {view.tab === "events" && <Events onDevice={openDevice} />}
    </div>
  );
}
