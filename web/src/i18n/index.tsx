import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { en } from "./en";
import type { MessageKey, Messages } from "./en";

export type Direction = "ltr" | "rtl";

interface Locale {
  code: string;
  dir: Direction;
  messages: Messages;
}

// Register new languages here. Hebrew comes later: { code: 'he', dir: 'rtl', messages: he }.
const LOCALES: Record<string, Locale> = {
  en: { code: "en", dir: "ltr", messages: en },
};

interface I18nValue {
  locale: string;
  dir: Direction;
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
  setDir: (dir: Direction) => void;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({
  locale = "en",
  children,
}: {
  locale?: string;
  children: ReactNode;
}) {
  const current = LOCALES[locale] ?? LOCALES.en;
  // The direction can be flipped on its own so we can test RTL layout before the Hebrew strings exist.
  const [dir, setDir] = useState<Direction>(current.dir);

  useEffect(() => {
    document.documentElement.lang = current.code;
    document.documentElement.dir = dir;
  }, [current.code, dir]);

  const t = useCallback(
    (key: MessageKey, vars?: Record<string, string | number>) => {
      let text: string = current.messages[key] ?? key;
      if (vars) {
        for (const [name, value] of Object.entries(vars))
          text = text.replaceAll(`{${name}}`, String(value));
      }
      return text;
    },
    [current],
  );

  const value = useMemo(() => ({ locale: current.code, dir, t, setDir }), [current.code, dir, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside <I18nProvider>");
  return ctx;
}
