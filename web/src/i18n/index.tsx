import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { en } from "./en";
import type { MessageKey, Messages } from "./en";
import { he } from "./he";

export type Direction = "ltr" | "rtl";
export type LocaleCode = "en" | "he";

interface Locale {
  dir: Direction;
  tag: string; // for Intl date formatting
  messages: Partial<Messages>;
}

// English is the default and the fallback for any missing key (PROJECT.md 6).
const LOCALES: Record<LocaleCode, Locale> = {
  en: { dir: "ltr", tag: "en-GB", messages: en },
  he: { dir: "rtl", tag: "he-IL", messages: he },
};
const STORE = "lang";

interface I18nValue {
  locale: LocaleCode;
  dir: Direction;
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
  toggleLocale: () => void;
  /** "5 minutes ago", in the current language. */
  relative: (iso: string) => string;
  /** Short date and time, in the current language. */
  absolute: (iso: string) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

function storedLocale(fallback: LocaleCode): LocaleCode {
  try {
    const saved = localStorage.getItem(STORE);
    return saved === "en" || saved === "he" ? saved : fallback;
  } catch {
    return fallback;
  }
}

export function I18nProvider({
  locale: initial = "en",
  children,
}: {
  locale?: LocaleCode;
  children: ReactNode;
}) {
  const [locale, setLocale] = useState<LocaleCode>(() => storedLocale(initial));
  const current = LOCALES[locale];

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = current.dir;
    try {
      localStorage.setItem(STORE, locale);
    } catch {
      // The choice is simply not remembered.
    }
  }, [locale, current.dir]);

  const t = useCallback(
    (key: MessageKey, vars?: Record<string, string | number>) => {
      let text: string = current.messages[key] ?? en[key] ?? key;
      if (vars) {
        for (const [name, value] of Object.entries(vars))
          text = text.replaceAll(`{${name}}`, String(value));
      }
      return text;
    },
    [current],
  );

  const value = useMemo<I18nValue>(() => {
    const relative = (iso: string) => {
      const minutes = Math.min(0, Math.round((Date.parse(iso) - Date.now()) / 60_000));
      const format = new Intl.RelativeTimeFormat(current.tag, { numeric: "auto" });
      const out =
        minutes > -60
          ? format.format(minutes, "minute")
          : minutes > -1440
            ? format.format(Math.round(minutes / 60), "hour")
            : format.format(Math.round(minutes / 1440), "day");
      return out.replace(" (1)", ""); // Hebrew adds it to the singular
    };
    const absolute = (iso: string) =>
      new Date(iso).toLocaleString(current.tag, { dateStyle: "short", timeStyle: "medium" });
    return {
      locale,
      dir: current.dir,
      t,
      toggleLocale: () => setLocale((l) => (l === "en" ? "he" : "en")),
      relative,
      absolute,
    };
  }, [locale, current, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside <I18nProvider>");
  return ctx;
}
