import { useCallback, useState } from "react";
import { Construction } from "lucide-react";
import { Toaster } from "sonner";
import { AppShell } from "./components/layout/AppShell";
import { MODULE_LIST } from "./components/layout/modules";
import { Button, EmptyState } from "./components/ui";
import { ChatPage } from "./features/chat/ChatPage";
import { InvestigatorPage } from "./features/investigator/InvestigatorPage";
import { useCriticalIncidentToasts } from "./features/investigator/useIncidents";
import { ChatchupTab } from "./features/pcap/ChatchupTab";
import { I18nProvider, useI18n } from "./i18n";
import { useTheme } from "./lib/theme";
import { useHashRoute } from "./lib/useHashRoute";

function Shell() {
  const [route, navigate] = useHashRoute();
  const { theme, toggle } = useTheme();
  const { t, dir } = useI18n();
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const module = MODULE_LIST.find((m) => m.id === route) ?? MODULE_LIST[1];

  const openIncident = useCallback(
    (id: string) => {
      navigate("investigator");
      setIncidentId(id);
    },
    [navigate],
  );
  useCriticalIncidentToasts(openIncident);

  function page() {
    switch (route) {
      case "chat":
        return <ChatPage />;
      case "investigator":
        return <InvestigatorPage selectedId={incidentId} onSelect={setIncidentId} />;
      case "pcap":
        return <ChatchupTab theme={theme} />;
      default:
        return (
          <EmptyState
            icon={<Construction size={28} />}
            title={t("placeholder.title", { module: t(module.label) })}
            body={t("placeholder.body")}
          >
            <Button variant="primary" onClick={() => navigate("chat")}>
              {t("placeholder.cta")}
            </Button>
          </EmptyState>
        );
    }
  }

  return (
    <>
      <AppShell
        active={route}
        title={t(module.label)}
        theme={theme}
        onNavigate={navigate}
        onToggleTheme={toggle}
      >
        {page()}
      </AppShell>
      <Toaster theme={theme} dir={dir} position="bottom-right" richColors closeButton />
    </>
  );
}

export default function App() {
  return (
    <I18nProvider>
      <Shell />
    </I18nProvider>
  );
}
