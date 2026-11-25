// Read-only tools the assistant may call. Same names and shapes as the future MCP / api tools
// (PROJECT.md 3, AI rule 2). Nothing here can change a device.
import type { Source } from "../types";
import { ALERTS, CONFIG_CHANGES, DEVICES, HOSTS, INTERFACES, LOGS } from "./network";
import type { Alert, ConfigChange, Device, Host, Interface, LogLine } from "./network";

export const READ_ONLY_TOOLS = [
  "get_device",
  "get_interface",
  "list_interfaces",
  "lookup_knowledge_base",
  "query_logs",
  "list_alerts",
  "get_config_changes",
  "find_host",
  "analyze_impact",
] as const;

export function getDevice(name: string): Device | undefined {
  return DEVICES.find((d) => d.name.toLowerCase() === name.toLowerCase());
}

export function getInterface(device: string, name: string): Interface | undefined {
  return INTERFACES.find(
    (i) =>
      i.device.toLowerCase() === device.toLowerCase() && normalizeIf(i.name) === normalizeIf(name),
  );
}

/** Finds the device that owns an interface when the user only names the port. */
export function findInterface(name: string): Interface | undefined {
  return INTERFACES.find((i) => normalizeIf(i.name) === normalizeIf(name));
}

export function queryLogs(device: string, contains?: string): LogLine[] {
  return LOGS.filter(
    (l) =>
      l.device === device &&
      (!contains || l.message.toLowerCase().includes(contains.toLowerCase())),
  );
}

export function listAlerts(): Alert[] {
  return ALERTS;
}

/** Config changes for one device, or for every device when none is given. */
export function getConfigChanges(device?: string): ConfigChange[] {
  return device ? CONFIG_CHANGES.filter((c) => c.device === device) : CONFIG_CHANGES;
}

export function listInterfaces(device: string): Interface[] {
  return INTERFACES.filter((i) => i.device === device);
}

export function findHost(ip: string): Host | undefined {
  return HOSTS.find((h) => h.ip === ip);
}

export function deviceSource(device: string): Source {
  const d = getDevice(device);
  return {
    id: `device:${device}`,
    kind: "device",
    label: device,
    detail: d ? `${d.vendor} ${d.model} · ${d.mgmtIp}` : undefined,
  };
}

export function logSource(line: LogLine): Source {
  return {
    // Several lines can share a second, so the message is part of the identity.
    id: `log:${line.device}:${line.time}:${line.message}`,
    kind: "log",
    label: `syslog ${line.device} ${line.time}`,
    detail: line.message,
  };
}

/** "Gi1/0/5", "gi 1/0/5" and "GigabitEthernet1/0/5" are the same port. */
export function normalizeIf(name: string): string {
  return name
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/^gigabitethernet/, "gi")
    .replace(/^tengigabitethernet/, "te")
    .replace(/^port-channel/, "po");
}
