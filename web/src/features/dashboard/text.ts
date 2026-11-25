import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/en";

// Dashboard strings live in the shared i18n files under "dash.*". This only adds the prefix.
type DashKey = MessageKey extends infer K ? (K extends `dash.${infer R}` ? R : never) : never;

export function useText() {
  const { t, relative, absolute } = useI18n();
  return { t: (key: DashKey) => t(`dash.${key}` as MessageKey), relative, absolute };
}
