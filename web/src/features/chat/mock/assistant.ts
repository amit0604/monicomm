// Mock ChatIAF assistant: stands in for the local LLM + tool calling until api/app/modules/chat exists.
// RULE (CLAUDE.md 3, docs §7.3): this module may only use read-only tools and draft proposals.
// It must never import the configurator. A test enforces that.
//
// Routing is done by the local rule-based classifier in ./intent.ts (not an AI model). A demo
// scenario runs only on an anchored match; everything else gets an honest knowledge-base answer,
// a guardrail reply, or a request to clarify.
import { severityToStatus } from "../../../components/ui/StatusPill";
import type { AssistantEvent, Cell, ReplyMeta, Source } from "../types";
import { isThanks, reply } from "./guardrails";
import { draftAction } from "./impact";
import type { Operation } from "./impact";
import { classify, wantsComparison } from "./intent";
import type { Classification, ConversationContext, Intent, Scenario } from "./intent";
import { entryById, lookup } from "./knowledge";
import type { KnowledgeEntry } from "./knowledge";
import {
  deviceSource,
  findHost,
  findInterface,
  getConfigChanges,
  getDevice,
  getInterface,
  listAlerts,
  listInterfaces,
  logSource,
  queryLogs,
} from "./tools";

export interface RespondOptions {
  signal?: AbortSignal;
  /** Milliseconds per streamed word / tool call. 0 in tests. */
  pace?: number;
  /** What earlier replies in this chat were about. Empty after "New chat". */
  context?: ConversationContext;
}

export const SUGGESTIONS = [
  "Why is Gi1/0/5 on access-sw-12 down?",
  "What changed on core-sw-01 since yesterday?",
  "Show active alerts",
  "Which switch is host 10.1.4.22 on?",
  "Shut down Gi1/0/48 on access-sw-12",
  "WAN to Site-North is slow. What can we do?",
  "What is the difference between TCP and UDP?",
];

/** Concepts that explain each demo finding, used by follow-ups like "why?" after a scenario. */
const SCENARIO_CONCEPTS: Partial<Record<Scenario, string[]>> = {
  port_down: ["stp"],
  wan: ["crc", "ospf"],
  config_changes: ["vlan", "ospf"],
  shutdown: ["vlan"],
  host: ["arp"],
};

export async function* respond(
  question: string,
  opts: RespondOptions = {},
): AsyncGenerator<AssistantEvent> {
  const conversation = opts.context ?? { turns: [] };
  const cls = classify(question, conversation);
  yield* answer(
    new Stream(opts.pace ?? 18, opts.signal),
    question.trim(),
    cls,
    conversation,
    false,
  );
}

function meta(
  cls: Classification,
  asMixed: boolean,
  extra: Partial<ReplyMeta> = {},
): AssistantEvent {
  return {
    type: "meta",
    meta: {
      intent: (asMixed ? "MIXED" : cls.intent) as Intent,
      confidence: cls.confidence,
      reason: cls.reason,
      engine: "rule-based classifier",
      concepts: [],
      entries: [],
      scenario: cls.scenario,
      ...extra,
    },
  };
}

async function* answer(
  ctx: Stream,
  q: string,
  cls: Classification,
  conversation: ConversationContext,
  asMixed: boolean,
): AsyncGenerator<AssistantEvent> {
  const lang = cls.lang;
  switch (cls.intent) {
    case "POLICY_VIOLATION":
      yield meta(cls, asMixed);
      yield* ctx.text(reply("policy", lang));
      return;
    case "GREETING":
      yield meta(cls, asMixed);
      yield* ctx.text(reply(isThanks(q) ? "thanks" : "greeting", lang));
      return;
    case "SYSTEM_CAPABILITIES":
      yield meta(cls, asMixed);
      yield* ctx.text(reply("capabilities", lang));
      return;
    case "DATA_PROVENANCE":
      yield meta(cls, asMixed);
      yield* ctx.text(reply("provenance", lang));
      return;
    case "PERMISSION_QUESTION":
      yield meta(cls, asMixed);
      yield* ctx.text(reply("permission", lang));
      return;
    case "OUT_OF_SCOPE":
      yield meta(cls, asMixed);
      yield* ctx.text(reply("outOfScope", lang));
      return;
    case "MIXED":
      yield* ctx.text(reply("mixedPrefix", lang) + "\n\n");
      yield* answer(ctx, q, cls.inScope!, conversation, true);
      return;
    case "AMBIGUOUS":
      yield meta(cls, asMixed);
      yield* ctx.text(reply(/follow-up/.test(cls.reason) ? "noContext" : "ambiguous", lang));
      return;
    case "TECHNICAL_KNOWLEDGE":
      yield* knowledgeFlow(ctx, cls, asMixed, lookup(cls.entities.concepts), false);
      return;
    case "FOLLOW_UP":
      yield* followUpFlow(ctx, q, cls, conversation);
      return;
    default:
      yield meta(cls, asMixed);
      if (lang === "he") yield* ctx.text(reply("scenarioEnglishOnly", lang) + "\n\n");
      yield* scenarioFlow(ctx, cls);
  }
}

function scenarioFlow(ctx: Stream, cls: Classification): AsyncGenerator<AssistantEvent> {
  const { device, iface, ip } = cls.entities;
  switch (cls.scenario) {
    case "shutdown":
      return shutdownFlow(ctx, iface!, device);
    case "port_down":
      return portDownFlow(ctx, iface!, device);
    case "wan":
      return wanFlow(ctx);
    case "config_changes":
      return changesFlow(ctx, device);
    case "alerts":
      return alertsFlow(ctx);
    case "host":
      return hostFlow(ctx, ip!);
    default:
      return deviceStatusFlow(ctx, device, iface);
  }
}

function knowledgeSource(entry: KnowledgeEntry): Source {
  return {
    id: `kb:${entry.id}`,
    kind: "knowledge",
    label: `Local knowledge base: ${entry.title.en}`,
    detail: "Static reference text bundled with the prototype, not generated by an AI model",
  };
}

async function* knowledgeFlow(
  ctx: Stream,
  cls: Classification,
  asMixed: boolean,
  entries: KnowledgeEntry[],
  withDetail: boolean,
  intro?: string,
  /** Follow-up on an entry already shown: give only the part the user hasn't seen. */
  detailOnly = false,
): AsyncGenerator<AssistantEvent> {
  const lang = cls.lang;
  if (entries.length === 0) {
    yield meta(cls, asMixed, { concepts: cls.entities.concepts });
    yield* ctx.text(reply("notInKb", lang));
    return;
  }

  yield meta(cls, asMixed, {
    engine: "local knowledge base",
    concepts: [...new Set(entries.flatMap((e) => e.covers))],
    entries: entries.map((e) => e.id),
    detailShown: withDetail,
  });
  yield* ctx.tool(
    "lookup_knowledge_base",
    { topic: entries.map((e) => e.id).join(",") },
    () => entries,
    (r) => `${r.length} local entr${r.length === 1 ? "y" : "ies"}`,
  );

  const body = entries
    .map((e) => {
      const text = detailOnly
        ? e.detail[lang]
        : `${e.summary[lang]}${withDetail ? `\n\n${e.detail[lang]}` : ""}`;
      return `**${e.title[lang]}** · ${reply("kbLabel", lang)}\n\n${text}`;
    })
    .join("\n\n");
  yield* ctx.text((intro ? `${intro}\n\n` : "") + body);
  yield { type: "sources", sources: entries.map(knowledgeSource) };
}

async function* followUpFlow(
  ctx: Stream,
  q: string,
  cls: Classification,
  conversation: ConversationContext,
): AsyncGenerator<AssistantEvent> {
  const lang = cls.lang;
  const last = conversation.turns.at(-1);
  const followCls: Classification = { ...cls, intent: "FOLLOW_UP" };

  if (last && (last.entries.length > 0 || last.concepts.length > 0)) {
    if (wantsComparison(q) && last.concepts.length >= 2) {
      const entries = lookup(last.concepts);
      if (entries.length === 1 && entries[0].covers.length >= 2) {
        yield* knowledgeFlow(ctx, followCls, false, entries, false);
        return;
      }
    }
    const entry = entryById(last.entries[0]) ?? lookup(last.concepts)[0];
    if (entry) {
      if (last.detailShown) {
        yield meta(followCls, false, {
          concepts: entry.covers,
          entries: [entry.id],
          detailShown: true,
          engine: "local knowledge base",
        });
        yield* ctx.text(reply("kbExhausted", lang, { title: entry.title[lang] }));
        return;
      }
      yield* knowledgeFlow(ctx, followCls, false, [entry], true, undefined, true);
      return;
    }
  }

  const related = last?.scenario ? SCENARIO_CONCEPTS[last.scenario] : undefined;
  if (related) {
    const entries = lookup(related);
    if (entries.length > 0) {
      yield* knowledgeFlow(ctx, followCls, false, entries, true, reply("backgroundFor", lang));
      return;
    }
  }

  yield meta(followCls, false);
  yield* ctx.text(reply(last ? "noContextTopic" : "noContext", lang));
}

async function* deviceStatusFlow(
  ctx: Stream,
  deviceName?: string,
  ifName?: string,
): AsyncGenerator<AssistantEvent> {
  const iface = ifName
    ? deviceName
      ? getInterface(deviceName, ifName)
      : findInterface(ifName)
    : undefined;
  const name = deviceName ?? iface?.device;
  const device = name
    ? yield* ctx.tool(
        "get_device",
        { device: name },
        () => getDevice(name),
        (d) => (d ? `${d.vendor} ${d.model} · ${d.status}` : "not found"),
      )
    : undefined;
  if (!device) {
    yield* ctx.text(
      `I couldn't find ${ifName ?? deviceName ?? "that"} in the inventory. Check the name, or ask "show active alerts".`,
    );
    return;
  }
  const ifaces = yield* ctx.tool(
    "list_interfaces",
    { device: device.name },
    () => (iface ? [iface] : listInterfaces(device.name)),
    (r) => `${r.length} monitored interface${r.length === 1 ? "" : "s"}`,
  );
  yield {
    type: "table",
    title: `${device.name} · ${device.vendor} ${device.model} · mgmt ${device.mgmtIp}`,
    columns: [
      { key: "name", label: "Interface", kind: "mono" },
      { key: "description", label: "Description" },
      { key: "state", label: "State", kind: "status" },
      { key: "util", label: "Utilization", kind: "num" },
      { key: "errors", label: "Errors 24h", kind: "num" },
    ],
    rows: ifaces.map((i) => ({
      name: i.name,
      description: i.description,
      state:
        i.oper === "up"
          ? status("Up", "ok")
          : status(i.oper === "err-disabled" ? "Err-disabled" : "Down", "critical"),
      util: `${i.utilization}%`,
      errors: i.errors24h,
    })),
  };
  const bad = ifaces.filter((i) => i.oper !== "up" || i.errors24h > 0);
  yield* ctx.text(
    `**${device.name} is ${device.status}.** ` +
      (bad.length
        ? `${bad.length} monitored interface${bad.length === 1 ? " needs" : "s need"} attention: ${bad.map((i) => `${i.name} (${i.oper !== "up" ? i.oper : `${i.errors24h} errors`})`).join(", ")}.`
        : "All monitored interfaces are up with no errors in the last 24 hours."),
  );
  yield { type: "sources", sources: [deviceSource(device.name)] };
}
/** Small helper so every flow streams tools and text the same way. */
class Stream {
  private toolCount = 0;
  constructor(
    private pace: number,
    private signal?: AbortSignal,
  ) {}

  async wait(ms: number) {
    if (this.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (ms <= 0) return;
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, ms);
      this.signal?.addEventListener(
        "abort",
        () => {
          clearTimeout(timer);
          reject(new DOMException("Aborted", "AbortError"));
        },
        { once: true },
      );
    });
  }

  async *tool<T>(
    tool: string,
    args: Record<string, string>,
    run: () => T,
    summarize: (r: T) => string,
  ) {
    const id = `tool-${++this.toolCount}`;
    yield { type: "tool_start", id, tool, args } as AssistantEvent;
    const started = performance.now();
    await this.wait(this.pace * 20);
    const result = run();
    yield {
      type: "tool_end",
      id,
      summary: summarize(result),
      durationMs: Math.round(performance.now() - started),
    } as AssistantEvent;
    return result;
  }

  async *text(text: string) {
    const words = text.split(/(\s+)/);
    for (const word of words) {
      await this.wait(this.pace);
      yield { type: "text_delta", text: word } as AssistantEvent;
    }
  }
}

function status(label: string, s: "ok" | "warning" | "critical" | "info" | "neutral"): Cell {
  return { status: s, label };
}

async function* portDownFlow(
  ctx: Stream,
  ifName: string,
  deviceName?: string,
): AsyncGenerator<AssistantEvent> {
  const iface = yield* ctx.tool(
    "get_interface",
    { device: deviceName ?? "?", interface: ifName },
    () => (deviceName ? getInterface(deviceName, ifName) : findInterface(ifName)),
    (r) =>
      r ? `${r.device} ${r.name}: oper ${r.oper}${r.reason ? ` (${r.reason})` : ""}` : "not found",
  );
  if (!iface) {
    yield* ctx.text(
      `I couldn't find ${ifName}${deviceName ? ` on ${deviceName}` : ""} in the inventory. Check the port name, or ask "show active alerts".`,
    );
    return;
  }

  const logs = yield* ctx.tool(
    "query_logs",
    { device: iface.device, interface: iface.name, range: "last 24h" },
    () => queryLogs(iface.device),
    (r) => `${r.length} matching syslog lines`,
  );

  yield {
    type: "table",
    title: `Syslog · ${iface.device} · last 24h`,
    columns: [
      { key: "time", label: "Time", kind: "mono" },
      { key: "severity", label: "Severity", kind: "status" },
      { key: "message", label: "Message", kind: "mono" },
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

  yield { type: "proposal", action: draftAction(iface, { kind: "bounce" }) };
  yield {
    type: "sources",
    sources: [deviceSource(iface.device), ...logs.slice(0, 3).map(logSource)],
  };
}

async function* shutdownFlow(
  ctx: Stream,
  ifName: string,
  deviceName?: string,
): AsyncGenerator<AssistantEvent> {
  const iface = yield* ctx.tool(
    "get_interface",
    { device: deviceName ?? "?", interface: ifName },
    () => (deviceName ? getInterface(deviceName, ifName) : findInterface(ifName)),
    (r) => (r ? `${r.mode} · ${r.activeHosts} active hosts · ${r.description}` : "not found"),
  );
  if (!iface) {
    yield* ctx.text(
      `I couldn't find ${ifName}${deviceName ? ` on ${deviceName}` : ""}. No change was drafted.`,
    );
    return;
  }

  const op: Operation = { kind: "shutdown" };
  const action = yield* ctx.tool(
    "analyze_impact",
    { device: iface.device, interface: iface.name, change: "shutdown" },
    () => draftAction(iface, op),
    (a) => `risk ${a.impact.risk} · ${a.impact.affected.length} affected items`,
  );

  if (action.impact.risk === "high") {
    yield* ctx.text(
      `⚠️ Before you approve: **${iface.name} is not an edge port.** It's the ${iface.mode} uplink to ${iface.neighbor}, ` +
        `carrying VLANs ${iface.vlan} for **${iface.activeHosts} active hosts**, and it's also how we reach ${iface.device} for management.\n\n` +
        `Shutting it isolates the whole switch. If you meant a desk port, tell me which one. If you really need this (for example, a planned uplink move), the drafted change is below.`,
    );
  } else {
    yield* ctx.text(
      `${iface.name} is an edge port (${iface.description}). The impact is limited to it. The drafted change is below.`,
    );
  }

  yield { type: "proposal", action };
  yield {
    type: "sources",
    sources: [
      deviceSource(iface.device),
      {
        id: `if:${iface.name}`,
        kind: "inventory",
        label: `${iface.device} ${iface.name}`,
        detail: iface.description,
      },
    ],
  };
}

async function* wanFlow(ctx: Stream): AsyncGenerator<AssistantEvent> {
  const primary = yield* ctx.tool(
    "get_interface",
    { device: "edge-rtr-01", interface: "xe-0/1/0" },
    () => getInterface("edge-rtr-01", "xe-0/1/0")!,
    (r) => `${r.utilization}% used · ${r.errors24h} CRC errors / 24h`,
  );
  const backup = yield* ctx.tool(
    "get_interface",
    { device: "edge-rtr-01", interface: "xe-0/1/1" },
    () => getInterface("edge-rtr-01", "xe-0/1/1")!,
    (r) => `${r.utilization}% used · ${r.errors24h} errors`,
  );
  const logs = yield* ctx.tool(
    "query_logs",
    { device: "edge-rtr-01", range: "last 24h" },
    () => queryLogs("edge-rtr-01"),
    (r) => `${r.length} syslog lines`,
  );

  yield {
    type: "table",
    title: "edge-rtr-01 · WAN links to Site-North",
    columns: [
      { key: "link", label: "Link", kind: "mono" },
      { key: "role", label: "Role" },
      { key: "state", label: "State", kind: "status" },
      { key: "util", label: "Utilization", kind: "num" },
      { key: "errors", label: "CRC errors 24h", kind: "num" },
    ],
    rows: [
      {
        link: primary.name,
        role: "Primary (OSPF cost 10)",
        state: status("Degraded", "critical"),
        util: `${primary.utilization}%`,
        errors: primary.errors24h,
      },
      {
        link: backup.name,
        role: "Backup (OSPF cost 50)",
        state: status("Healthy", "ok"),
        util: `${backup.utilization}%`,
        errors: backup.errors24h,
      },
    ],
  };

  yield* ctx.text(
    `The primary WAN link **xe-0/1/0 is the bottleneck**: 92% utilization plus 1,840 CRC errors in 24 hours. ` +
      `It flapped at 07:12 and the OSPF neighbor dropped to Init for a moment. CRC errors on a 10G link usually point to a dirty or failing optic or fiber.\n\n` +
      `The backup link xe-0/1/1 is healthy and almost idle. A safe short-term fix is to **raise the OSPF cost on xe-0/1/0** so traffic prefers the backup, ` +
      `then replace the optic in a maintenance window. This is a router change, so it needs **two approvers**.`,
  );

  yield { type: "proposal", action: draftAction(primary, { kind: "ospf_cost", cost: 100 }) };
  yield { type: "sources", sources: [deviceSource("edge-rtr-01"), ...logs.map(logSource)] };
}

async function* changesFlow(ctx: Stream, deviceName?: string): AsyncGenerator<AssistantEvent> {
  // No device named: look across all devices rather than guessing one.
  const scope = deviceName ?? "all devices";
  const changes = yield* ctx.tool(
    "get_config_changes",
    { device: deviceName ?? "all", since: "yesterday 00:00" },
    () => getConfigChanges(deviceName),
    (r) => `${r.length} change${r.length === 1 ? "" : "s"}`,
  );

  if (changes.length === 0) {
    yield* ctx.text(`No config changes on ${scope} since yesterday in the mock data.`);
    if (deviceName) yield { type: "sources", sources: [deviceSource(deviceName)] };
    return;
  }

  const devices = [...new Set(changes.map((c) => c.device))];
  const users = [...new Set(changes.map((c) => c.user))];
  yield {
    type: "table",
    title: `Config changes · ${scope}`,
    columns: [
      { key: "time", label: "When", kind: "mono" },
      { key: "device", label: "Device", kind: "mono" },
      { key: "user", label: "Who", kind: "mono" },
      { key: "summary", label: "What" },
    ],
    rows: changes.map((c) => ({
      time: c.time,
      device: c.device,
      user: c.user,
      summary: c.summary,
    })),
  };
  yield {
    type: "code",
    title: "Diff (running config)",
    language: "diff",
    content: changes.map((c) => c.diff).join("\n"),
  };

  const alerts = listAlerts().filter((a) => devices.includes(a.device));
  const ospf = changes.find((c) => /ospf cost/i.test(c.summary));
  yield* ctx.text(
    `**${changes.length} change${changes.length === 1 ? "" : "s"} on ${devices.join(", ")} since yesterday, by ${users.join(", ")}:** ` +
      changes
        .map((c) => `${c.summary.charAt(0).toLowerCase()}${c.summary.slice(1)} (${c.time})`)
        .join("; ") +
      "." +
      (alerts.length
        ? `\n\nThat lines up with alert **${alerts[0].id}** ("${alerts[0].title}") at ${alerts[0].since}.` +
          (ospf
            ? ` The OSPF cost change probably pushed that traffic onto a longer path. Worth checking with ${ospf.user} whether it was intended.`
            : "")
        : ""),
  );
  yield {
    type: "sources",
    sources: [
      ...devices.map(deviceSource),
      ...changes.map<Source>((c) => ({
        id: `cfg:${c.device}:${c.time}`,
        kind: "config",
        label: `config ${c.device} ${c.time}`,
        detail: c.summary,
      })),
      ...alerts.map<Source>((a) => ({ id: a.id, kind: "alert", label: a.id, detail: a.title })),
    ],
  };
}

async function* alertsFlow(ctx: Stream): AsyncGenerator<AssistantEvent> {
  const alerts = yield* ctx.tool(
    "list_alerts",
    { state: "active" },
    () => listAlerts(),
    (r) => `${r.length} active alerts`,
  );
  yield {
    type: "table",
    title: "Active alerts",
    columns: [
      { key: "severity", label: "Severity", kind: "status" },
      { key: "id", label: "ID", kind: "mono" },
      { key: "device", label: "Device", kind: "mono" },
      { key: "title", label: "Alert" },
      { key: "since", label: "Since", kind: "mono" },
    ],
    rows: alerts.map((a) => ({
      severity: status(
        a.severity === "critical" ? "Critical" : a.severity === "warning" ? "Warning" : "Info",
        a.severity,
      ),
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
  yield {
    type: "sources",
    sources: alerts.map<Source>((a) => ({ id: a.id, kind: "alert", label: a.id, detail: a.title })),
  };
}

async function* hostFlow(ctx: Stream, ip: string): AsyncGenerator<AssistantEvent> {
  const host = yield* ctx.tool(
    "find_host",
    { ip },
    () => findHost(ip),
    (r) => (r ? `${r.device} ${r.port}` : "not in ARP/MAC tables"),
  );
  if (!host) {
    yield* ctx.text(
      `${ip} isn't in any ARP or MAC table right now. It may be offline, or on a segment we don't poll yet.`,
    );
    return;
  }
  const iface = getInterface(host.device, host.port);
  yield {
    type: "table",
    title: `Host ${ip}`,
    columns: [
      { key: "hostname", label: "Hostname", kind: "mono" },
      { key: "mac", label: "MAC", kind: "mono" },
      { key: "switch", label: "Switch", kind: "mono" },
      { key: "port", label: "Port", kind: "mono" },
      { key: "vlan", label: "VLAN", kind: "num" },
      { key: "state", label: "Port state", kind: "status" },
    ],
    rows: [
      {
        hostname: host.hostname,
        mac: host.mac,
        switch: host.device,
        port: host.port,
        vlan: host.vlan,
        state:
          iface?.oper === "up"
            ? status("Up", "ok")
            : status(iface?.oper === "err-disabled" ? "Err-disabled" : "Down", "critical"),
      },
    ],
  };
  const device = getDevice(host.device);
  yield* ctx.text(
    `**${host.hostname} (${ip}) is on ${host.device} port ${host.port}, VLAN ${host.vlan}.**` +
      (iface && iface.oper !== "up"
        ? ` That port is currently **${iface.oper}**, so the host is offline. Ask "why is ${host.port} on ${host.device} down?" for the cause.`
        : "") +
      (device ? `\n\nSwitch: ${device.vendor} ${device.model}, mgmt ${device.mgmtIp}.` : ""),
  );
  yield {
    type: "sources",
    sources: [
      deviceSource(host.device),
      {
        id: `arp:${ip}`,
        kind: "inventory",
        label: `MAC table ${host.device}`,
        detail: `${host.mac} on ${host.port}`,
      },
    ],
  };
}
