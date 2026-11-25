import { Activity, FileSearch, LayoutDashboard, MessagesSquare, Network, Siren } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { MessageKey } from '../../i18n/en';
import type { ModuleId } from '../../lib/useHashRoute';

export interface ModuleInfo {
  id: ModuleId;
  label: MessageKey;
  icon: LucideIcon;
  accentVar: string;
}

// Fixed order from PROJECT.md 6A.
export const MODULE_LIST: ModuleInfo[] = [
  { id: 'dashboard', label: 'nav.dashboard', icon: LayoutDashboard, accentVar: '--module-dashboard' },
  { id: 'chat', label: 'nav.chat', icon: MessagesSquare, accentVar: '--module-chat' },
  { id: 'analyzer', label: 'nav.analyzer', icon: Activity, accentVar: '--module-analyzer' },
  { id: 'investigator', label: 'nav.investigator', icon: Siren, accentVar: '--module-investigator' },
  { id: 'mapper', label: 'nav.mapper', icon: Network, accentVar: '--module-mapper' },
  { id: 'pcap', label: 'nav.pcap', icon: FileSearch, accentVar: '--module-pcap' },
];
