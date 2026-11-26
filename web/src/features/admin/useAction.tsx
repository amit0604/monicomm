import { useState } from "react";
import { StatusPill } from "../../components/ui";
import { useI18n } from "../../i18n";
import type { MessageKey } from "../../i18n/en";
import { AdminError } from "./api";

export interface Notice {
  ok: boolean;
  key: MessageKey;
  vars?: Record<string, string | number>;
}

export const errorKey = (e: unknown): MessageKey =>
  e instanceof AdminError ? `admin.error.${e.code}` : "admin.error.failed";

/** One request at a time per panel (save, test, reset) and the notice it leaves. */
export function useAction<Name extends string>() {
  const [busy, setBusy] = useState<Name | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  async function run(name: Name, work: () => Promise<Notice>) {
    setBusy(name);
    setNotice(null);
    try {
      setNotice(await work());
    } catch (e) {
      setNotice({ ok: false, key: errorKey(e) });
    }
    setBusy(null);
  }

  return { busy, notice, setNotice, run };
}

export function NoticeLine({ notice }: { notice: Notice | null }) {
  const { t } = useI18n();
  if (!notice) return null;
  return (
    <div role={notice.ok ? "status" : "alert"}>
      <StatusPill status={notice.ok ? "ok" : "critical"} label={t(notice.key, notice.vars)} />
    </div>
  );
}
