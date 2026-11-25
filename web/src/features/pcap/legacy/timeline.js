// Traffic-over-time bar chart (packets per bucket) as inline SVG, plus the time-window overlay.
import { fmt, svg } from "./ui.js";

const HEIGHT = 112, LEFT = 44, BOTTOM = 20, TOP = 6;

export function renderTimeline(container, caption, { buckets, duration, bucket_s }) {
  container.replaceChildren();
  if (!buckets.length) return;
  const width = container.clientWidth || 800;
  const plotW = width - LEFT;
  const plotH = HEIGHT - BOTTOM - TOP;
  const max = Math.max(...buckets.map((b) => b.packets), 1);
  const root = svg("svg", { viewBox: `0 0 ${width} ${HEIGHT}`, preserveAspectRatio: "none", role: "img", "aria-label": "Packets over time" });

  for (const f of [0, 0.5, 1]) {
    const y = TOP + plotH * (1 - f);
    root.append(svg("line", { class: "cc-gridline", x1: LEFT, x2: width, y1: y, y2: y }));
    const label = svg("text", { class: "cc-axis", x: LEFT - 8, y: y + 4, "text-anchor": "end" });
    label.textContent = fmt.number(Math.round(max * f));
    root.append(label);
  }
  const slot = plotW / buckets.length;
  buckets.forEach((b, i) => {
    const h = (b.packets / max) * plotH;
    const rect = svg("rect", { class: "cc-bar", x: LEFT + i * slot + 1, y: TOP + plotH - h, width: Math.max(slot - 2, 1), height: Math.max(h, 0), rx: 2 });
    const title = svg("title");
    title.textContent = `${fmt.clock(b.t)}–${fmt.clock(b.t + bucket_s)}: ${fmt.number(b.packets)} packets, ${fmt.bytes(b.bytes)}`;
    rect.append(title);
    root.append(rect);
  });
  for (const f of [0, 0.25, 0.5, 0.75, 1]) {
    const label = svg("text", { class: "cc-axis", x: LEFT + plotW * f, y: HEIGHT - 4, "text-anchor": f === 0 ? "start" : f === 1 ? "end" : "middle" });
    label.textContent = fmt.clock(duration * f);
    root.append(label);
  }
  container.append(root);
  caption.textContent = `IP packets per ${bucket_s.toFixed(1)} s · peak ${fmt.number(max)}`;
}

export function setWindowOverlay(container, startFraction, endFraction) {
  const root = container.querySelector("svg");
  if (!root) return;
  const width = Number(root.getAttribute("viewBox").split(" ")[2]);
  const plotW = width - LEFT;
  let rect = root.querySelector("rect.cc-window");
  if (!rect) {
    rect = svg("rect", { class: "cc-window" });
    root.append(rect);
  }
  const full = startFraction <= 0 && endFraction >= 1;
  rect.toggleAttribute("hidden", full);
  if (full) return;
  rect.setAttribute("x", LEFT + startFraction * plotW);
  rect.setAttribute("y", TOP);
  rect.setAttribute("width", Math.max((endFraction - startFraction) * plotW, 1));
  rect.setAttribute("height", HEIGHT - BOTTOM - TOP);
}
