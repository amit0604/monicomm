// Catchup tab (temporary plain-JS version, adapted from the PCAP Lab workshop UI).
// Embeds in the Monicomm shell as one tab:
//   import { mountCatchup } from "./features/pcap/legacy/index.js";   // + catchup.css, vendor/cytoscape
//   const tab = mountCatchup(containerEl, { apiBase: "/api/v1/pcap" });  // tab.destroy() on leave
// Everything is scoped under the container (.catchup); no global ids, styles or listeners.
// To be ported to React (web/src/features/pcap/) once the shell and shared components exist.
import { createApi } from "./api.js";
import { createGraph } from "./graph.js";
import { renderHost, renderOverview, renderPair } from "./inspector.js";
import { renderTimeline, setWindowOverlay } from "./timeline.js";
import { el, fmt, pill, toast } from "./ui.js";

const TEMPLATE = `
<div class="cc-toolbar">
  <label class="cc-field"><span class="cc-muted cc-small">Capture</span><select data-ref="captures" aria-label="Open a capture"></select></label>
  <span data-ref="status"></span>
  <span class="cc-spacer"></span>
  <button class="cc-btn" data-ref="upload">Upload capture</button>
  <input type="file" data-ref="file" accept=".pcap,.pcapng,.cap" hidden>
</div>

<div data-ref="start" class="cc-start">
  <div class="cc-dropzone" data-ref="dropzone" tabindex="0" role="button">
    <strong>Drop a .pcap / .pcapng file here</strong> or click to browse
    <div class="cc-muted cc-small">Parsed on the server, in the background. Nothing leaves the network.</div>
  </div>
</div>

<div data-ref="workspace" class="cc-workspace" hidden>
  <div class="cc-kpis" data-ref="kpis"></div>
  <div class="cc-network">
    <div class="cc-panel cc-graph-panel">
      <div class="cc-panel-toolbar">
        <div class="cc-segmented" data-ref="protocols" role="group" aria-label="Protocol filter">
          <button class="cc-active" data-protocol="">All</button><button data-protocol="TCP">TCP</button>
          <button data-protocol="UDP">UDP</button><button data-protocol="ICMP">ICMP</button>
        </div>
        <label class="cc-field cc-slider"><span class="cc-small">Min packets <b data-ref="minval">1</b></span>
          <input type="range" data-ref="min" min="1" max="50" value="1"></label>
        <input type="search" data-ref="search" placeholder="Find host (IP)…" aria-label="Find host" autocomplete="off">
        <span class="cc-spacer"></span>
        <span class="cc-muted cc-small">Ctrl + scroll to zoom</span>
        <button class="cc-icon" data-ref="fit" title="Fit to screen" aria-label="Fit to screen">⤢</button>
        <button class="cc-icon" data-ref="relayout" title="Re-arrange" aria-label="Re-arrange">↻</button>
      </div>
      <div class="cc-graph-wrap">
        <div class="cc-graph" data-ref="graph"></div>
        <div class="cc-empty" data-ref="graphEmpty" hidden>No conversations match these filters.</div>
        <div class="cc-legend">
          <span><i class="cc-swatch cc-sw-int"></i>Internal</span><span><i class="cc-swatch cc-sw-ext"></i>External</span>
          <span><i class="cc-swatch cc-sw-hub"></i>Hub</span><span><i class="cc-swatch cc-sw-sus"></i>Suspicious</span>
          <span><i class="cc-line cc-l-tcp"></i>TCP</span><span><i class="cc-line cc-l-udp"></i>UDP</span>
          <span><i class="cc-line cc-l-icmp"></i>ICMP</span><span><i class="cc-line cc-l-mixed"></i>Mixed</span>
        </div>
      </div>
    </div>
    <aside class="cc-panel cc-inspector" data-ref="inspector" aria-live="polite"></aside>
  </div>
  <div class="cc-panel">
    <div class="cc-panel-head"><h3>Traffic over time</h3><span class="cc-muted cc-small" data-ref="caption"></span></div>
    <div data-ref="timeline" class="cc-timeline"></div>
    <div class="cc-window-track">
      <input type="range" data-ref="twStart" min="0" max="1" step="0.001" value="0" aria-label="Window start">
      <input type="range" data-ref="twEnd" min="0" max="1" step="0.001" value="1" aria-label="Window end">
    </div>
    <div class="cc-window-labels"><span data-ref="twStartLabel">0:00</span>
      <button class="cc-btn cc-btn-ghost" data-ref="twClear" hidden>Clear window</button><span data-ref="twEndLabel">0:00</span></div>
  </div>
</div>
<div class="cc-toast" data-ref="toast" role="status" hidden></div>`;

export function mountCatchup(root, { apiBase = "/api/v1/pcap" } = {}) {
  // After destroy() a late API reply must not touch the removed DOM: replies then never settle,
  // so no continuation (render, toast, polling) runs.
  let alive = true;
  const never = () => new Promise(() => {});
  const api = Object.fromEntries(
    Object.entries(createApi(apiBase)).map(([name, call]) => [
      name,
      (...args) =>
        call(...args).then(
          (value) => (alive ? value : never()),
          (error) => (alive ? Promise.reject(error) : never()),
        ),
    ]),
  );
  root.classList.add("catchup");
  root.innerHTML = TEMPLATE; // static markup only; capture data always goes in via textContent
  const $ = (ref) => root.querySelector(`[data-ref="${ref}"]`);
  const state = {
    id: null,
    capture: null,
    timeline: null,
    graph: null,
    protocol: "",
    minPackets: 1,
    tStart: null,
    tEnd: null,
    overview: null,
  };
  const timers = new Set();
  const later = (fn, ms) => {
    const t = setTimeout(() => {
      timers.delete(t);
      fn();
    }, ms);
    timers.add(t);
    return t;
  };
  const fail = (err) => toast(root, err.message);

  const graph = createGraph($("graph"), {
    onNode: (ip) => showHost(ip),
    onEdge: (edge) => renderPair($("inspector"), edge, actions),
    onClear: () => showOverview(),
  });
  const actions = {
    onBack: () => {
      graph.clear();
      showOverview();
    },
    onHost: (ip) => selectHost(ip),
  };
  const ai = { summary: () => api.summary(state.id), ask: (q) => api.ask(state.id, q) };

  // ---------- captures: list, upload, processing ----------

  async function refreshList(selectId) {
    const list = await api.list();
    const select = $("captures");
    select.replaceChildren(
      el("option", { value: "" }, list.length ? "Choose a capture…" : "No captures yet"),
      ...list.map((c) =>
        el("option", { value: c.id }, `${c.filename} · ${fmt.bytes(c.size)} · ${c.status}`),
      ),
    );
    if (selectId) select.value = selectId;
  }

  async function upload(file) {
    try {
      setStatus(pill("info", `Uploading ${file.name}…`));
      const meta = await api.upload(file);
      await refreshList(meta.id);
      await open(meta.id);
    } catch (err) {
      setStatus(pill("critical", "Upload failed"));
      fail(err);
    }
  }

  function setStatus(node) {
    $("status").replaceChildren(node || "");
  }

  async function open(id) {
    if (!id) return;
    const capture = await api.capture(id);
    state.id = id;
    if (capture.status === "queued" || capture.status === "processing") {
      setStatus(pill("info", `Analyzing ${capture.filename}…`));
      later(() => open(id).catch(fail), 700);
      return;
    }
    if (capture.status === "failed") {
      setStatus(pill("critical", `Failed: ${capture.error}`));
      return;
    }
    setStatus(
      pill(
        "ok",
        `${fmt.number(capture.analysis.packet_count)} packets · ${fmt.duration(capture.analysis.duration_s)}`,
      ),
    );
    refreshList(id).catch(fail); // status in the picker is now "done"
    state.capture = capture;
    Object.assign(state, { protocol: "", minPackets: 1, tStart: null, tEnd: null });
    root
      .querySelectorAll("[data-protocol]")
      .forEach((b) => b.classList.toggle("cc-active", b.dataset.protocol === ""));
    $("min").value = 1;
    $("minval").textContent = "1";
    $("start").hidden = true;
    $("workspace").hidden = false;
    requestAnimationFrame(() => graph.resize());

    state.timeline = await api.timeline(id);
    const duration = state.timeline.duration;
    for (const r of ["twStart", "twEnd"])
      Object.assign($(r), { min: 0, max: duration, step: duration / 1000 || 0.001 });
    renderTimeline($("timeline"), $("caption"), state.timeline);
    setWindow(0, duration);
    await refresh();
    showOverview();
  }

  // ---------- network view ----------

  const win = () => ({ tStart: state.tStart, tEnd: state.tEnd });

  async function refresh() {
    const [g, o] = await Promise.all([
      api.graph(state.id, { protocol: state.protocol, minPackets: state.minPackets, ...win() }),
      api.overview(state.id, win()),
    ]);
    state.graph = g;
    state.overview = o;
    $("graphEmpty").hidden = g.nodes.length > 0;
    graph.render(g);
    renderKpis(o, g);
  }

  function renderKpis(o, g) {
    const kpi = (label, value, sub) =>
      el(
        "div",
        { class: "cc-panel cc-kpi" },
        el("div", { class: "cc-muted cc-small" }, label),
        el("div", { class: "cc-kpi-value" }, value),
        el("div", { class: "cc-muted cc-small" }, sub || " "),
      );
    $("kpis").replaceChildren(
      kpi("Packets", fmt.number(o.packets)),
      kpi(
        "Hosts",
        fmt.number(g.nodes.length),
        `${g.nodes.filter((n) => n.internal).length} internal`,
      ),
      kpi("Host pairs", fmt.number(g.edges.length)),
      kpi("Data", fmt.bytes(o.bytes)),
      kpi("Duration", fmt.duration(o.duration), fmt.datetime(o.start)),
      kpi(
        "Findings",
        fmt.number(o.suspicious.length),
        o.suspicious.length ? "scan / beacon" : "none",
      ),
    );
  }

  function showOverview() {
    if (state.overview) renderOverview($("inspector"), state.overview, { onHost: selectHost, ai });
  }

  async function showHost(ip) {
    try {
      const host = await api.host(state.id, ip);
      renderHost(
        $("inspector"),
        host,
        state.graph.nodes.find((n) => n.id === ip),
        graph.edgesOf(ip),
        actions,
      );
    } catch (err) {
      fail(err);
    }
  }

  function selectHost(ip) {
    if (graph.select(ip)) showHost(ip);
    else toast(root, `${ip} is not in the graph with the current filters.`);
  }

  // ---------- time window ----------

  function setWindow(start, end) {
    const duration = state.timeline.duration || 1;
    $("twStart").value = start;
    $("twEnd").value = end;
    $("twStartLabel").textContent = fmt.clock(start);
    $("twEndLabel").textContent = fmt.clock(end);
    setWindowOverlay($("timeline"), start / duration, end / duration);
    $("twClear").hidden = !(start > 0.001 || end < duration - 0.001);
  }

  let twTimer = null;
  function onWindowInput() {
    if (!state.timeline) return;
    const duration = state.timeline.duration;
    let start = Number($("twStart").value);
    const end = Number($("twEnd").value);
    if (start > end) start = end;
    setWindow(start, end);
    clearTimeout(twTimer);
    twTimer = later(async () => {
      state.tStart = start < 0.001 ? null : start;
      state.tEnd = end > duration - 0.001 ? null : end;
      await refresh().catch(fail);
      showOverview();
    }, 250);
  }

  // ---------- wiring (all listeners live on elements inside root) ----------

  $("twStart").addEventListener("input", onWindowInput);
  $("twEnd").addEventListener("input", onWindowInput);
  $("twClear").addEventListener("click", () => {
    setWindow(0, state.timeline.duration);
    onWindowInput();
  });
  $("captures").addEventListener("change", (e) => open(e.target.value).catch(fail));
  $("upload").addEventListener("click", () => $("file").click());
  $("file").addEventListener("change", () => {
    const file = $("file").files[0];
    $("file").value = "";
    if (file) upload(file);
  });
  const dz = $("dropzone");
  dz.addEventListener("click", () => $("file").click());
  dz.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && $("file").click());
  dz.addEventListener("dragover", (e) => {
    e.preventDefault();
    dz.classList.add("cc-over");
  });
  dz.addEventListener("dragleave", () => dz.classList.remove("cc-over"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault();
    dz.classList.remove("cc-over");
    if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
  });
  root.querySelectorAll("[data-protocol]").forEach((button) =>
    button.addEventListener("click", async () => {
      state.protocol = button.dataset.protocol;
      root
        .querySelectorAll("[data-protocol]")
        .forEach((b) => b.classList.toggle("cc-active", b === button));
      await refresh().catch(fail);
      showOverview();
    }),
  );
  let minTimer = null;
  $("min").addEventListener("input", (e) => {
    state.minPackets = Number(e.target.value);
    $("minval").textContent = state.minPackets;
    clearTimeout(minTimer);
    minTimer = later(async () => {
      await refresh().catch(fail);
      showOverview();
    }, 200);
  });
  $("search").addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !state.graph) return;
    const q = e.target.value.trim();
    const match =
      state.graph.nodes.find((n) => n.id === q) ||
      state.graph.nodes.find((n) => n.id.startsWith(q));
    if (match) selectHost(match.id);
    else toast(root, `No host matching "${q}".`);
  });
  $("fit").addEventListener("click", () => graph.fit());
  $("relayout").addEventListener("click", () => graph.relayout());

  // Re-draw the timeline when the tab changes size (side nav collapse, window resize).
  const resize = new ResizeObserver(() => {
    if (!state.timeline || $("workspace").hidden) return;
    renderTimeline($("timeline"), $("caption"), state.timeline);
    setWindow(Number($("twStart").value), Number($("twEnd").value));
    graph.resize();
  });
  resize.observe(root);

  refreshList().catch(fail);

  return {
    open: (id) => refreshList(id).then(() => open(id)),
    // Call after the shell switches theme: the graph and chart re-read the tokens.
    reload: () => state.id && state.timeline && refresh().then(showOverview).catch(fail),
    destroy() {
      alive = false;
      timers.forEach(clearTimeout);
      resize.disconnect();
      graph.destroy();
      root.replaceChildren();
      root.classList.remove("catchup");
    },
  };
}
