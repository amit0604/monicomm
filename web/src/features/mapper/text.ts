import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/en";

// Mapper strings live in the shared i18n files under "map.*". This only adds the prefix.
type MapKey = MessageKey extends infer K ? (K extends `map.${infer R}` ? R : never) : never;

export function useMapText() {
  const { t } = useI18n();
  return {
    t: (key: MapKey, vars?: Record<string, string | number>) => t(`map.${key}` as MessageKey, vars),
    /** Shared keys, e.g. the Dashboard's device statuses and types, so both pages say the same. */
    raw: t,
  };
}
