import { Construction } from 'lucide-react';
import { Toaster } from 'sonner';
import { AppShell } from './components/layout/AppShell';
import { MODULE_LIST } from './components/layout/modules';
import { EmptyState } from './components/ui';
import { ChatPage } from './features/chat/ChatPage';
import { useI18n } from './i18n';
import { useTheme } from './lib/theme';
import { useHashRoute } from './lib/useHashRoute';

export function App() {
  const route = useHashRoute();
  const { theme, toggle } = useTheme();
  const { t, dir } = useI18n();
  const module = MODULE_LIST.find((m) => m.id === route) ?? MODULE_LIST[1];

  return (
    <>
      <AppShell active={route} title={t(module.label)} theme={theme} onToggleTheme={toggle}>
        {route === 'chat' ? (
          <ChatPage />
        ) : (
          <EmptyState
            icon={<Construction size={28} />}
            title={t('placeholder.title', { module: t(module.label) })}
            body={t('placeholder.body')}
          >
            <a className="btn btn--primary" href="#/chat">
              {t('placeholder.cta')}
            </a>
          </EmptyState>
        )}
      </AppShell>
      <Toaster theme={theme} dir={dir} position="bottom-right" richColors closeButton />
    </>
  );
}
