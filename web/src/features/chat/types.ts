// ChatIAF data model. These shapes are the contract with the future api/app/modules/chat,
// which streams them as JSON events. The API uses snake_case (PROJECT.md 7); map it in the backend adapter.
import type { Status } from "../../components/ui";
import type { Classification, TurnContext } from "./mock/intent";

export interface Source {
  id: string;
  kind: "device" | "log" | "metric" | "config" | "alert" | "inventory" | "knowledge";
  label: string;
  detail?: string;
  /** Fabricated data. Defaults to true for every non-knowledge source (the in-browser mock). */
  mock?: boolean;
}

export type Cell = string | number | { status: Status; label: string };

export interface Column {
  key: string;
  label: string;
  kind?: "text" | "mono" | "status" | "num";
}

export type Part =
  | { type: "text"; text: string }
  | {
      type: "tool_call";
      id: string;
      tool: string;
      args: Record<string, string>;
      status: "running" | "done" | "error";
      summary?: string;
      durationMs?: number;
    }
  | { type: "table"; title?: string; columns: Column[]; rows: Record<string, Cell>[] }
  | { type: "code"; title?: string; language: "cli" | "diff" | "log"; content: string }
  | { type: "action"; actionId: string };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "configurator";
  createdAt: number;
  parts: Part[];
  sources?: Source[];
  streaming?: boolean;
  meta?: ReplyMeta;
}

/** How a reply was produced. Shown in the UI so a rule-based answer is never mistaken for a model's. */
export interface ReplyMeta extends TurnContext {
  confidence: Classification["confidence"];
  reason: string;
  engine: "rule-based classifier" | "local knowledge base" | "model";
}

export type Risk = "low" | "medium" | "high";

export type DeviceRole =
  | "access-switch"
  | "distribution-switch"
  | "core-switch"
  | "router"
  | "firewall";

export interface Impact {
  risk: Risk;
  summary: string;
  affected: { label: string; detail: string; status: Status }[];
  warnings: string[];
  safetyNet: string;
}

export type ActionStatus =
  | "pending"
  | "awaiting_second"
  | "applying"
  | "verifying"
  | "applied"
  | "cancelled"
  | "failed"
  | "rolled_back";

export interface ActionResult {
  checks: { label: string; ok: boolean }[];
  output: string;
}

/** A change the AI drafted. Only a human approval can move it past 'pending'. */
export interface ProposedAction {
  id: string;
  title: string;
  device: { name: string; role: DeviceRole };
  method: "snmp-set" | "netconf" | "cli";
  commands: string;
  rollback: string;
  impact: Impact;
  approvalsRequired: 1 | 2;
  approvals: string[];
  approvalId?: string;
  status: ActionStatus;
  result?: ActionResult;
}

/** Events the assistant streams for one reply (mock now, HTTP/WebSocket later). */
export type AssistantEvent =
  | { type: "meta"; meta: ReplyMeta }
  | { type: "tool_start"; id: string; tool: string; args: Record<string, string> }
  | { type: "tool_end"; id: string; summary: string; durationMs: number }
  | { type: "text_delta"; text: string }
  | { type: "table"; title?: string; columns: Column[]; rows: Record<string, Cell>[] }
  | { type: "code"; title?: string; language: "cli" | "diff" | "log"; content: string }
  | { type: "proposal"; action: ProposedAction }
  | { type: "sources"; sources: Source[] };
