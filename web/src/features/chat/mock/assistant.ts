// Mock ChatIAF assistant: stands in for the local LLM + tool calling until api/app/modules/chat exists.
// RULE (CLAUDE.md 3, docs §7.3): this module may only use read-only tools and draft proposals.
// It must never import the configurator. A test enforces that.
import { severityToStatus } from '../../../components/ui/StatusPill';
import type { AssistantEvent, Cell, Source } from '../types';
import { draftAction } from './impact';
import type { Operation } from './impact';
import {
  deviceSource,
  findHost,
  findInterface,
  getConfigChanges,
  getDevice,
  getInterface,
  listAlerts,
  logSource,
  queryLogs,
} from './tools';
import { DEVICES } from './network';

export interface RespondOptions {
  signal?: AbortSignal;
  /** Milliseconds per streamed word / tool call. 0 in tests. */
  pace?: number;
}

export const SUGGESTIONS = [
  'Why is Gi1/0/5 on access-sw-12 down?',
  'What changed on core-sw-01 since yesterday?',
  'Show active alerts',
  'Which switch is host 10.1.4.22 on?',
  'Shut down Gi1/0/48 on access-sw-12',
  'WAN to Site-North is slow. What can we do?',
];

const DEVICE_RE = new RegExp(`\\b(${DEVICES.map((d) => d.name).join('|')})\\b`, 'i');
const IF_RE = /\b((?:gi(?:gabitethernet)?|te|xe|po)[-\d/]*\d)\b/i;
const IP_RE = /\b(\d{1,3}(?:\.\d{1,3}){3})\b/;

export async function* respond(question: string, opts: RespondOptions = {}): AsyncGenerator<AssistantEvent> {
  const pace = opts.pace ?? 18;
  const q = question.trim();
  const lower = q.toLowerCase();
  const deviceName = q.match(DEVICE_RE)?.[1]?.toLowerCase();
  const ifName = q.match(IF_RE)?.[1];
  const ip = q.match(IP_RE)?.[1];

  const ctx = new Stream(pace, opts.signal);

  if (/\b(shut|disable|turn off|bring down)\b/.test(lower) && ifName) {
    yield* shutdownFlow(ctx, ifName, deviceName);
  } else if (ifName && /\b(down|why|err|recover|fix|broken|not working)\b/.test(lower)) {
    yield* portDownFlow(ctx, ifName, deviceName);
  } else if (/\b(wan|slow|crc|ospf|cost|reroute|site-north|edge-rtr-01)\b/.test(lower)) {
    yield* wanFlow(ctx);
  } else if (/\b(chang|config|diff|who did)/.test(lower)) {
    yield* changesFlow(ctx, deviceName ?? 'core-sw-01');
  } else if (/\balert/.test(lower)) {
    yield* alertsFlow(ctx);
  } else if (ip) {
    yield* hostFlow(ctx, ip);
  } else {
    yield* helpFlow(ctx);
  }
}

/** Small helper so every flow streams tools and text the same way. */
class Stream {
  private toolCount = 0;
  constructor(
    private pace: number,
    private signal?: AbortSignal,
  ) {}

  async wait(ms: number) {
    if (this.signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    if (ms <= 0) return;
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, ms);
      this.signal?.addEventListener(
        'abort',
        () => {
          clearTimeout(timer);
          reject(new DOMException('Aborted', 'AbortError'));
        },
        { once: true },
      );
    });
  }

  async *tool<T>(tool: string, args: Record<string, string>, run: () => T, summarize: (r: T) => string) {
    const id = `tool-${++this.toolCount}`;
    yield { type: 'tool_start', id, tool, args } as AssistantEvent;
    const started = performance.now();
    await this.wait(this.pace * 20);
    const result = run();
    yield { type: 'tool_end', id, summary: summarize(result), durationMs: Math.round(performance.now() - started) } as AssistantEvent;
    return result;
  }

  async *text(text: string) {
    const words = text.split(/(\s+)/);
    for (const word of words) {
      await this.wait(this.pace);
      yield { type: 'text_delta', text: word } as AssistantEvent;
    }
  }
}

function status(label: string, s: 'ok' | 'warning' | 'critical' | 'info' | 'neutral'): Cell {
  return { status: s, label };
}

async function* portDownFlow(ctx: Stream, ifName: string, deviceName?: string): AsyncGenerator<AssistantEvent> {
  const iface = yield* ctx.tool(
    'get_interface',
    { device: deviceName ?? '?', interface: ifName },
    () => (deviceName ? getInterface(deviceName, ifName) : findInterface(ifName)),
    (r) => (r ? `${r.device} ${r.name}: oper ${r.oper}${r.reason ? ` (${r.reason})` : ''}` : 'not found'),
  );
  if (!iface) {
    yield* ctx.text(`I couldn't find ${ifName}${deviceName ? ` on ${deviceName}` : ''} in the inventory. Check the port name, or ask "show active alerts".`);
    return;
  }

  const logs = yield* ctx.tool(
    'query_logs',
    { device: iface.device, interface: iface.name, range: 'last 24h' },
    () => queryLogs(iface.device),
    (r) => `${r.length} matching syslog lines`,
  );

  yield {
    type: 'table',
    title: `Syslog · ${iface.device} · last 24h`,
    columns: [
      { key: 'time', label: 'Time', kind: 'mono' },
      { key: 'severity', label: 'Severity', kind: 'status' },
      { key: 'message', label: 'Message', kind: 'mono' },
    ],
    rows: logs
      .slice()
      .sort((a, b) => a.time.localeCompare(b.time))
      .map((l) => ({
        time: l.time,
        severity: { status: severityToStatus(l.severity), label: l.severity },
        message: l.message,
      })),
  };

  yield* ctx.text(
    `**${iface.name} on ${iface.device} is err-disabled by BPDU Guard** since 09:41:07.\n\n` +
      `16 seconds earlier LLDP saw a new neighbor on that port: a **TP-Link TL-SG105 unmanaged switch**. ` +
      `Someone plugged a small switch into the LAB-05 desk port, it sent BPDUs, and the switch shut the port to protect the spanning tree. ` +
      `The host behind it, **PC-LAB-05 (10.1.4.22)**, is offline.\n\n` +
      `Recommended: remove the unmanaged switch at the desk, then recover the port. I prepared the change below. It runs only if you approve it.`,
  );

  yield { type: 'proposal', action: draftAction(iface, { kind: 'bounce' }) };
  yield {
    type: 'sources',
    sources: [deviceSource(iface.device), ...logs.slice(0, 3).map(logSource)],
  };
}

async function* shutdownFlow(ctx: Stream, ifName: string, deviceName?: string): AsyncGenerator<AssistantEvent> {
  const iface = yield* ctx.tool(
    'get_interface',
    { device: deviceName ?? '?', interface: ifName },
    () => (deviceName ? getInterface(deviceName, ifName) : findInterface(ifName)),
    (r) => (r ? `${r.mode} · ${r.activeHosts} active hosts · ${r.description}` : 'not found'),
  );
  if (!iface) {
    yield* ctx.text(`I couldn't find ${ifName}${deviceName ? ` on ${deviceName}` : ''}. No change was drafted.`);
    return;
  }

  const op: Operation = { kind: 'shutdown' };
  const action = yield* ctx.tool(
    'analyze_impact',
    { device: iface.device, interface: iface.name, change: 'shutdown' },
    () => draftAction(iface, op),
    (a) => `risk ${a.impact.risk} · ${a.impact.affected.length} affected items`,
  );

  if (action.impact.risk === 'high') {
    yield* ctx.text(
      `⚠️ Before you approve: **${iface.name} is not an edge port.** It's the ${iface.mode} uplink to ${iface.neighbor}, ` +
        `carrying VLANs ${iface.vlan} for **${iface.activeHosts} active hosts**, and it's also how we reach ${iface.device} for management.\n\n` +
        `Shutting it isolates the whole switch. If you meant a desk port, tell me which one. If you really need this (for example, a planned uplink move), the drafted change is below.`,
    );
  } else {
    yield* ctx.text(`${iface.name} is an edge port (${iface.description}). The impact is limited to it. The drafted change is below.`);
  }

  yield { type: 'proposal', action };
  yield { type: 'sources', sources: [deviceSource(iface.device), { id: `if:${iface.name}`, kind: 'inventory', label: `${iface.device} ${iface.name}`, detail: iface.description }] };
}

async function* wanFlow(ctx: Stream): AsyncGenerator<AssistantEvent> {
  const primary = yield* ctx.tool(
    'get_interface',
    { device: 'edge-rtr-01', interface: 'xe-0/1/0' },
    () => getInterface('edge-rtr-01', 'xe-0/1/0')!,
    (r) => `${r.utilization}% used · ${r.errors24h} CRC errors / 24h`,
  );
  const backup = yield* ctx.tool(
    'get_interface',
    { device: 'edge-rtr-01', interface: 'xe-0/1/1' },
    () => getInterface('edge-rtr-01', 'xe-0/1/1')!,
    (r) => `${r.utilization}% used · ${r.errors24h} errors`,
  );
  const logs = yield* ctx.tool(
    'query_logs',
    { device: 'edge-rtr-01', range: 'last 24h' },
    () => queryLogs('edge-rtr-01'),
    (r) => `${r.length} syslog lines`,
  );

  yield {
    type: 'table',
    title: 'edge-rtr-01 · WAN links to Site-North',
    columns: [
      { key: 'link', label: 'Link', kind: 'mono' },
      { key: 'role', label: 'Role' },
      { key: 'state', label: 'State', kind: 'status' },
      { key: 'util', label: 'Utilization', kind: 'num' },
      { key: 'errors', label: 'CRC errors 24h', kind: 'num' },
    ],
    rows: [
      { link: primary.name, role: 'Primary (OSPF cost 10)', state: status('Degraded', 'critical'), util: `${primary.utilization}%`, errors: primary.errors24h },
      { link: backup.name, role: 'Backup (OSPF cost 50)', state: status('Healthy', 'ok'), util: `${backup.utilization}%`, errors: backup.errors24h },
    ],
  };

  yield* ctx.text(
    `The primary WAN link **xe-0/1/0 is the bottleneck**: 92% utilization plus 1,840 CRC errors in 24 hours. ` +
      `It flapped at 07:12 and the OSPF neighbor dropped to Init for a moment. CRC errors on a 10G link usually point to a dirty or failing optic or fiber.\n\n` +
      `The backup link xe-0/1/1 is healthy and almost idle. A safe short-term fix is to **raise the OSPF cost on xe-0/1/0** so traffic prefers the backup, ` +
      `then replace the optic in a maintenance window. This is a router change, so it needs **two approvers**.`,
  );

  yield { type: 'proposal', action: draftAction(primary, { kind: 'ospf_cost', cost: 100 }) };
  yield { type: 'sources', sources: [deviceSource('edge-rtr-01'), ...logs.map(logSource)] };
}

async function* changesFlow(ctx: Stream, deviceName: string): AsyncGenerator<AssistantEvent> {
  const changes = yield* ctx.tool(
    'get_config_changes',
    { device: deviceName, since: 'yesterday 00:00' },
    () => getConfigChanges(deviceName),
    (r) => `${r.length} change${r.length === 1 ? '' : 's'}`,
  );

  if (changes.length === 0) {
    yield* ctx.text(`No config changes on ${deviceName} since yesterday.`);
    yield { type: 'sources', sources: [deviceSource(deviceName)] };
    return;
  }

  yield {
    type: 'table',
    title: `Config changes · ${deviceName}`,
    columns: [
      { key: 'time', label: 'When', kind: 'mono' },
      { key: 'user', label: 'Who', kind: 'mono' },
      { key: 'summary', label: 'What' },
    ],
    rows: changes.map((c) => ({ time: c.time, user: c.user, summary: c.summary })),
  };
  yield { type: 'code', title: 'Diff (running config)', language: 'diff', content: changes.map((c) => c.diff).join('\n') };

  const alerts = listAlerts().filter((a) => a.device === deviceName);
  yield* ctx.text(
    `**${changes.length} changes on ${deviceName}, both by netops-dana last night.** VLAN 30 was added to the Po1 trunk, and two minutes later the OSPF cost on the Vlan30 SVI went from 10 to 200.\n\n` +
      (alerts.length
        ? `That lines up with alert **${alerts[0].id}** ("${alerts[0].title}") at ${alerts[0].since}. The cost change probably pushed VLAN 30 traffic onto a longer path. Worth checking with Dana whether 200 was intended.`
        : ''),
  );
  yield {
    type: 'sources',
    sources: [
      deviceSource(deviceName),
      ...changes.map<Source>((c) => ({ id: `cfg:${c.time}`, kind: 'config', label: `config ${c.time}`, detail: c.summary })),
      ...alerts.map<Source>((a) => ({ id: a.id, kind: 'alert', label: a.id, detail: a.title })),
    ],
  };
}

async function* alertsFlow(ctx: Stream): AsyncGenerator<AssistantEvent> {
  const alerts = yield* ctx.tool('list_alerts', { state: 'active' }, () => listAlerts(), (r) => `${r.length} active alerts`);
  yield {
    type: 'table',
    title: 'Active alerts',
    columns: [
      { key: 'severity', label: 'Severity', kind: 'status' },
      { key: 'id', label: 'ID', kind: 'mono' },
      { key: 'device', label: 'Device', kind: 'mono' },
      { key: 'title', label: 'Alert' },
      { key: 'since', label: 'Since', kind: 'mono' },
    ],
    rows: alerts.map((a) => ({
      severity: status(a.severity === 'critical' ? 'Critical' : a.severity === 'warning' ? 'Warning' : 'Info', a.severity),
      id: a.id,
      device: a.device,
      title: a.title,
      since: a.since,
    })),
  };
  yield* ctx.text(
    `**${alerts.length} active alerts, 1 critical.** The critical one is the WAN link on edge-rtr-01 (CRC errors, 92% load). ` +
      `Ask "WAN to Site-North is slow" and I'll dig in, or "Why is Gi1/0/5 on access-sw-12 down?" for the access-port issue.`,
  );
  yield { type: 'sources', sources: alerts.map<Source>((a) => ({ id: a.id, kind: 'alert', label: a.id, detail: a.title })) };
}

async function* hostFlow(ctx: Stream, ip: string): AsyncGenerator<AssistantEvent> {
  const host = yield* ctx.tool('find_host', { ip }, () => findHost(ip), (r) => (r ? `${r.device} ${r.port}` : 'not in ARP/MAC tables'));
  if (!host) {
    yield* ctx.text(`${ip} isn't in any ARP or MAC table right now. It may be offline, or on a segment we don't poll yet.`);
    return;
  }
  const iface = getInterface(host.device, host.port);
  yield {
    type: 'table',
    title: `Host ${ip}`,
    columns: [
      { key: 'hostname', label: 'Hostname', kind: 'mono' },
      { key: 'mac', label: 'MAC', kind: 'mono' },
      { key: 'switch', label: 'Switch', kind: 'mono' },
      { key: 'port', label: 'Port', kind: 'mono' },
      { key: 'vlan', label: 'VLAN', kind: 'num' },
      { key: 'state', label: 'Port state', kind: 'status' },
    ],
    rows: [
      {
        hostname: host.hostname,
        mac: host.mac,
        switch: host.device,
        port: host.port,
        vlan: host.vlan,
        state: iface?.oper === 'up' ? status('Up', 'ok') : status(iface?.oper === 'err-disabled' ? 'Err-disabled' : 'Down', 'critical'),
      },
    ],
  };
  const device = getDevice(host.device);
  yield* ctx.text(
    `**${host.hostname} (${ip}) is on ${host.device} port ${host.port}, VLAN ${host.vlan}.**` +
      (iface && iface.oper !== 'up' ? ` That port is currently **${iface.oper}**, so the host is offline. Ask "why is ${host.port} on ${host.device} down?" for the cause.` : '') +
      (device ? `\n\nSwitch: ${device.vendor} ${device.model}, mgmt ${device.mgmtIp}.` : ''),
  );
  yield { type: 'sources', sources: [deviceSource(host.device), { id: `arp:${ip}`, kind: 'inventory', label: `MAC table ${host.device}`, detail: `${host.mac} on ${host.port}` }] };
}

async function* helpFlow(ctx: Stream): AsyncGenerator<AssistantEvent> {
  yield* ctx.text(
    `I can read devices, ports, syslog, alerts and config history, and explain what I find with sources. ` +
      `I can also **draft** a change with an impact analysis, but I can't apply anything. Only you can approve it.\n\nTry one of these:`,
  );
  yield {
    type: 'table',
    columns: [{ key: 'q', label: 'Example questions' }],
    rows: SUGGESTIONS.map((q) => ({ q })),
  };
}
