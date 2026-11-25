// ChatIAF software policy: rules the CODE enforces, whatever any model says.
// Model guidance lives separately in api/app/ai/prompts/chat_live.md and is not enforced by it.
import type { DeviceRole } from "./types";

/** What ChatIAF answers about. Anything else is declined (greetings, thanks and capability questions are fine). */
export const IN_SCOPE_DOMAINS = [
  "Networking",
  "Computer communications",
  "IT infrastructure",
  "OSI model",
  "TCP/IP",
  "Routing and switching concepts",
  "DNS and DHCP",
  "Network monitoring",
  "Servers and infrastructure",
  "Logs and alerts",
  "Defensive cybersecurity",
  "Technical troubleshooting concepts",
  "Root cause findings",
  "Impact assessment",
  "MoniComm product usage",
] as const;

export const OUT_OF_SCOPE_EXAMPLES = [
  "politics",
  "investments",
  "sports",
  "movies and TV",
  "relationships",
  "personal chat",
] as const;

/**
 * Read-only rule (CLAUDE.md 3, docs/plans/syslog-snmp-deployment.md §7.3), enforced by structure:
 * - the assistant gets read-only tools only (mock/tools.ts) and never imports the configurator (tested);
 * - a proposed change is created in 'pending' and only the approval UI (useChat.approve) can move it on;
 * - in this prototype the "configurator" is a local mock: no device, network or external service is contacted.
 */
export const READ_ONLY = true;

/** Docs §7.2: a second approver is required for routers, firewalls and core switches. */
export function approvalsRequiredFor(role: DeviceRole): 1 | 2 {
  return role === "router" || role === "firewall" || role === "core-switch" ? 2 : 1;
}

/** Prototype status, shown in the UI and used by the "is this real?" answers. Change these when a real backend lands. */
export const PROTOTYPE = {
  mockData: true,
  simulatedAi: true,
  modelConnected: false,
  networkConnected: false,
} as const;
