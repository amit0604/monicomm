// DOM and formatting helpers. Text always goes in through textContent, never innerHTML,
// so values from a capture (hostnames, URIs) cannot inject markup.

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "style") node.style.cssText = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function svg(tag, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag); // airgap: allow (XML namespace id, never fetched)
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

export const fmt = {
  number: (n) => Number(n || 0).toLocaleString("en-US"),
  bytes(n) {
    n = Number(n || 0);
    if (n < 1024) return `${n} B`;
    if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
    if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
    return `${(n / 1024 ** 3).toFixed(2)} GB`;
  },
  duration(seconds) {
    seconds = Number(seconds || 0);
    if (seconds < 60) return `${seconds.toFixed(1)} s`;
    return `${Math.floor(seconds / 60)} min ${String(Math.round(seconds % 60)).padStart(2, "0")} s`;
  },
  clock(seconds) {
    return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
  },
  datetime(epoch) {
    return epoch
      ? new Date(epoch * 1000).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "medium" })
      : "";
  },
};

// Reads a design token from web/src/styles/tokens.css (canvas drawing can't use var()).
export function token(root, name) {
  return getComputedStyle(root).getPropertyValue(name).trim();
}

// Status is never color alone: pill = icon + text, colored by status (PROJECT.md 6A).
const STATUS_ICON = { ok: "●", warning: "◐", critical: "▲", info: "ℹ", neutral: "○", accent: "◆" };
export function pill(status, text) {
  return el(
    "span",
    { class: `cc-pill cc-${status}` },
    el("span", { "aria-hidden": "true" }, STATUS_ICON[status]),
    text,
  );
}

export function toast(root, message) {
  const box = root.querySelector('[data-ref="toast"]');
  box.textContent = message;
  box.hidden = false;
  clearTimeout(box._timer);
  box._timer = setTimeout(() => (box.hidden = true), 6000);
}
