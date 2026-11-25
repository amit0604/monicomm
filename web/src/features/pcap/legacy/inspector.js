// Right-hand panel: capture overview (findings, AI, protocols, top talkers/ports),
// or details of the selected host or host pair.
import { el, fmt, pill } from "./ui.js";

const FINDING = { port_scan: ["critical", "Port scan"], beacon: ["critical", "Beacon"] };

function section(title, ...children) {
  return el("section", { class: "cc-section" }, title ? el("h3", {}, title) : null, ...children);
}

function scopeBadge(ip, internal) {
  return el(
    "span",
    { class: `cc-tag ${internal ? "cc-int" : "cc-ext"}` },
    internal ? "int" : "ext",
  );
}

function findings(list, onHost) {
  if (!list.length) return null;
  return section(
    "Findings",
    el(
      "ul",
      { class: "cc-findings" },
      list.map((f) => {
        const [status, label] = FINDING[f.type] || ["warning", f.type];
        return el(
          "li",
          {},
          pill(status, label),
          " ",
          el("span", { class: "cc-mono cc-muted" }, `#${f.packet}`),
          el("div", {}, f.message),
          el(
            "div",
            {},
            f.hosts.map((ip) =>
              el("button", { class: "cc-link cc-mono", onclick: () => onHost(ip) }, ip),
            ),
          ),
        );
      }),
    ),
  );
}

function aiPanel(ai) {
  const out = el(
    "div",
    { class: "cc-ai-out" },
    el("div", { class: "cc-muted" }, "Summary not generated yet."),
  );
  const show = (text, sources) =>
    out.replaceChildren(
      el("div", { class: "cc-ai-text" }, text),
      el(
        "div",
        { class: "cc-muted cc-small" },
        sources.length ? `Sources: ${sources.map((n) => `#${n}`).join(", ")}` : "No packet cited",
      ),
    );
  const fail = (err) => out.replaceChildren(pill("warning", err.message));
  const input = el("input", {
    type: "text",
    placeholder: "Ask about this capture…",
    "aria-label": "Question about this capture",
  });
  const ask = async () => {
    const q = input.value.trim();
    if (!q) return;
    out.replaceChildren(el("div", { class: "cc-muted" }, "Thinking…"));
    try {
      const r = await ai.ask(q);
      input.value = "";
      show(r.content, r.sources);
    } catch (err) {
      fail(err);
    }
  };
  input.addEventListener("keydown", (e) => e.key === "Enter" && ask());
  const summarize = async () => {
    out.replaceChildren(el("div", { class: "cc-muted" }, "Summarizing…"));
    try {
      const s = await ai.summary();
      show(s.text, s.sources);
    } catch (err) {
      fail(err);
    }
  };
  return el(
    "section",
    { class: "cc-section cc-ai" },
    el("h3", {}, el("span", { class: "cc-tag cc-ai-tag" }, "AI"), " Assistant"),
    el(
      "div",
      { class: "cc-row" },
      el("button", { class: "cc-btn cc-btn-secondary", onclick: summarize }, "Summarize capture"),
    ),
    out,
    el("div", { class: "cc-row" }, input, el("button", { class: "cc-btn", onclick: ask }, "Ask")),
  );
}

export function renderOverview(panel, summary, { onHost, ai }) {
  const total = summary.packets || 1;
  panel.replaceChildren(
    ...[
      summary.window
        ? el(
            "div",
            { class: "cc-note" },
            `Time window ${fmt.clock(summary.window.t_start)}–${fmt.clock(summary.window.t_end)} (±${summary.precision_s} s)`,
          )
        : null,
      findings(summary.suspicious, onHost),
      aiPanel(ai),
      section(
        "Protocols",
        el(
          "div",
          { class: "cc-bars" },
          Object.entries(summary.protocols).map(([name, count]) =>
            el(
              "div",
              { class: "cc-bar-row" },
              el("span", {}, name),
              el(
                "div",
                { class: "cc-bar-track" },
                el("div", { class: "cc-bar-fill", style: `width:${(count / total) * 100}%` }),
              ),
              el("span", { class: "cc-num" }, `${((count / total) * 100).toFixed(1)}%`),
            ),
          ),
        ),
      ),
      section(
        "Top talkers",
        el(
          "table",
          { class: "cc-mini" },
          el(
            "tbody",
            {},
            summary.top_talkers.map((h) =>
              el(
                "tr",
                {
                  class: "cc-click",
                  tabindex: "0",
                  title: "Show this host",
                  onclick: () => onHost(h.ip),
                  onkeydown: (e) => e.key === "Enter" && onHost(h.ip),
                },
                el(
                  "td",
                  {},
                  el("span", { class: "cc-mono" }, h.ip),
                  " ",
                  scopeBadge(h.ip, h.internal),
                ),
                el("td", { class: "cc-num" }, fmt.bytes(h.bytes)),
              ),
            ),
          ),
        ),
      ),
      section(
        "Top ports",
        el(
          "table",
          { class: "cc-mini" },
          el(
            "tbody",
            {},
            summary.top_ports.map((p) =>
              el(
                "tr",
                {},
                el(
                  "td",
                  {},
                  el("span", { class: "cc-mono" }, `${p.protocol} ${p.port}`),
                  p.service ? el("span", { class: "cc-muted" }, ` ${p.service}`) : null,
                ),
                el("td", { class: "cc-num" }, `${fmt.number(p.packets)} pkts`),
              ),
            ),
          ),
        ),
      ),
    ].filter(Boolean),
  );
}

function stat(label, value, sub) {
  return el(
    "div",
    { class: "cc-stat" },
    el("div", { class: "cc-muted cc-small" }, label),
    el("div", { class: "cc-stat-value" }, value),
    sub ? el("div", { class: "cc-muted cc-small" }, sub) : null,
  );
}

function backRow(onBack) {
  return el(
    "div",
    { class: "cc-row" },
    el("button", { class: "cc-link", onclick: onBack }, "← Overview"),
  );
}

export function renderHost(panel, host, node, edges, { onBack, onHost }) {
  const peers = edges
    .map((e) => ({
      ip: e.source === host.ip ? e.target : e.source,
      bytes: e.bytes,
      services: e.services,
    }))
    .sort((a, b) => b.bytes - a.bytes);
  panel.replaceChildren(
    section(
      null,
      backRow(onBack),
      el("div", { class: "cc-host-title cc-mono" }, host.ip),
      el(
        "div",
        { class: "cc-row" },
        pill(host.internal ? "info" : "accent", host.internal ? "Internal" : "External"),
        node?.hub ? pill("neutral", "Hub") : null,
        node?.suspicious ? pill("critical", "Suspicious") : null,
      ),
    ),
    findings(
      host.findings.map((f) => ({ ...f, message: f.detail })),
      onHost,
    ),
    section(
      null,
      el(
        "div",
        { class: "cc-stat-grid" },
        stat("Sent", fmt.bytes(host.bytes_sent), `${fmt.number(host.packets_sent)} packets`),
        stat(
          "Received",
          fmt.bytes(host.bytes_received),
          `${fmt.number(host.packets_received)} packets`,
        ),
        stat("Peers", fmt.number(host.peers)),
        stat("Protocols", host.protocols.join(", ")),
      ),
      el(
        "div",
        { class: "cc-muted cc-small" },
        `Active ${fmt.datetime(host.first_seen)} – ${fmt.datetime(host.last_seen)}`,
      ),
    ),
    section(
      `Talks to (${peers.length} in view)`,
      el(
        "table",
        { class: "cc-mini" },
        el(
          "tbody",
          {},
          peers.map((p) =>
            el(
              "tr",
              {
                class: "cc-click",
                tabindex: "0",
                onclick: () => onHost(p.ip),
                onkeydown: (e) => e.key === "Enter" && onHost(p.ip),
              },
              el(
                "td",
                {},
                el("span", { class: "cc-mono" }, p.ip),
                p.services.length
                  ? el("span", { class: "cc-muted" }, ` ${p.services.join(", ")}`)
                  : null,
              ),
              el("td", { class: "cc-num" }, fmt.bytes(p.bytes)),
            ),
          ),
        ),
      ),
    ),
  );
}

export function renderPair(panel, edge, { onBack, onHost }) {
  panel.replaceChildren(
    section(
      null,
      backRow(onBack),
      el("h3", {}, "Conversation"),
      el(
        "div",
        { class: "cc-pair" },
        el("button", { class: "cc-link cc-mono", onclick: () => onHost(edge.source) }, edge.source),
        el("span", { class: "cc-muted" }, "⇅"),
        el("button", { class: "cc-link cc-mono", onclick: () => onHost(edge.target) }, edge.target),
      ),
    ),
    section(
      null,
      el(
        "div",
        { class: "cc-stat-grid" },
        stat("Packets", fmt.number(edge.packets)),
        stat("Data", fmt.bytes(edge.bytes)),
        stat("Protocols", edge.protocols.join(", ")),
        stat("Services", edge.services.join(", ") || "—"),
      ),
    ),
  );
}
