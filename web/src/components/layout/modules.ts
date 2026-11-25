import {
  Activity,
  FileSearch,
  LayoutDashboard,
  MessagesSquare,
  Network,
  Siren,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { MessageKey } from "../../i18n/en";
import { MODULES, type ModuleId } from "../../modules";

export interface ModuleInfo {
  id: ModuleId;
  label: MessageKey;
  icon: LucideIcon;
}

const LABELS: Record<ModuleId, MessageKey> = {
  dashboard: "nav.dashboard",
  chat: "nav.chat",
  analyzer: "nav.analyzer",
  investigator: "nav.investigator",
  mapper: "nav.mapper",
  pcap: "nav.pcap",
};

const ICONS: Record<ModuleId, LucideIcon> = {
  dashboard: LayoutDashboard,
  chat: MessagesSquare,
  analyzer: Activity,
  investigator: Siren,
  mapper: Network,
  pcap: FileSearch,
};

// Same fixed order as src/modules.ts (PROJECT.md 6A); this adds the nav label key and icon.
// Each module's accent color is the token --accent-<id>.
export const MODULE_LIST: ModuleInfo[] = MODULES.map((m) => ({
  id: m.id,
  label: LABELS[m.id],
  icon: ICONS[m.id],
}));
