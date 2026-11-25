import cytoscape from "cytoscape";
import type { Core, ElementDefinition } from "cytoscape";
import { useEffect, useRef } from "react";
import type { DeviceType, LinkStatus, MapLink, MapNode } from "./api";
import { DEVICE_TONE, LINK_LINE, LINK_TONE, MEDIUM_TOKEN, shortPort } from "./model";

export type Selection = { kind: "node" | "link"; id: string } | null;

const SHAPES: Record<DeviceType, string> = {
  router: "ellipse",
  switch: "round-rectangle",
  firewall: "octagon",
  server: "rectangle",
  access_point: "triangle",
  unknown: "ellipse",
};

/** Text that rides on a link that isn't up: a symbol and a word, so status never hangs on color. */
const MARKS: Record<LinkStatus, string> = { up: "", degraded: "▲", down: "✕", unknown: "?" };

const token = (el: Element, name: string) => getComputedStyle(el).getPropertyValue(name).trim();

/**
 * A color token in a form Cytoscape can read. Tokens may use modern syntax (rgb(… / 18%)) or
 * point at other tokens; the browser's computed color is always rgb()/rgba() with commas.
 */
function color(el: Element, name: string): { rgb: string; alpha: number } {
  const probe = document.createElement("span");
  probe.style.color = `var(${name})`;
  el.appendChild(probe);
  const computed = getComputedStyle(probe).color;
  probe.remove();
  const [r = 0, g = 0, b = 0, alpha = 1] = (computed.match(/[\d.]+/g) ?? []).map(Number);
  return { rgb: `rgb(${r}, ${g}, ${b})`, alpha };
}

const rgb = (el: Element, name: string) => color(el, name).rgb;

/** A see-through token (dark theme "-soft" colors) laid over the surface, so nodes stay opaque. */
function solid(el: Element, name: string): string {
  const top = color(el, name);
  if (top.alpha >= 1) return top.rgb;
  const [over, under] = [top.rgb, rgb(el, "--surface")].map((c) => c.match(/\d+/g)!.map(Number));
  const mix = (i: number) => Math.round(over[i] * top.alpha + under[i] * (1 - top.alpha));
  return `rgb(${mix(0)}, ${mix(1)}, ${mix(2)})`;
}

function stylesheet(el: Element): Record<string, unknown>[] {
  const mono = token(el, "--font-mono") || "monospace";
  const label = {
    "font-family": mono,
    "font-size": 10,
    color: rgb(el, "--text"),
    "text-background-color": rgb(el, "--surface"),
    "text-background-opacity": 0.85,
    "text-background-padding": 2,
  };
  return [
    {
      selector: "node",
      style: {
        ...label,
        shape: "data(shape)",
        width: 34,
        height: 34,
        "background-color": "data(fill)",
        "border-color": "data(stroke)",
        "border-width": 2,
        label: "data(label)",
        "text-wrap": "wrap",
        "text-valign": "bottom",
        "text-margin-y": 6,
      },
    },
    { selector: "node.unknown-type", style: { "border-style": "dashed" } },
    {
      selector: "edge",
      style: {
        ...label,
        "font-size": 9,
        width: 3,
        "curve-style": "bezier",
        "line-color": "data(color)",
        "line-style": "data(line)",
        "source-label": "data(aPort)",
        "target-label": "data(bPort)",
        "source-text-offset": 30,
        "target-text-offset": 30,
        label: "data(mark)",
        color: rgb(el, "--text-muted"),
      },
    },
    { selector: "edge.down", style: { opacity: 0.75 } },
    { selector: "edge.unknown", style: { "line-dash-pattern": [2, 6] } },
    {
      selector: ":selected",
      style: {
        "overlay-color": rgb(el, "--primary"),
        "overlay-opacity": 0.18,
        "overlay-padding": 6,
      },
    },
  ];
}

function elements(
  host: Element,
  nodes: MapNode[],
  links: MapLink[],
  text: { device: (n: MapNode) => string; link: (s: LinkStatus) => string },
): ElementDefinition[] {
  const tone = (status: string) => ({
    fill: solid(host, `--${status}-soft`),
    stroke: rgb(host, `--${status}-strong`),
  });
  return [
    ...nodes.map((n) => ({
      group: "nodes" as const,
      classes: n.type === "unknown" ? "unknown-type" : undefined,
      data: {
        id: n.id,
        shape: SHAPES[n.type],
        label: text.device(n),
        ...tone(DEVICE_TONE[n.status]),
      },
    })),
    ...links.map((l) => ({
      group: "edges" as const,
      classes: l.status,
      data: {
        id: l.id,
        source: l.a.device_id,
        target: l.b.device_id,
        color: rgb(host, MEDIUM_TOKEN[l.medium]),
        line: LINK_LINE[l.status],
        aPort: shortPort(l.a.port),
        bPort: shortPort(l.b.port),
        mark: l.status === "up" ? "" : `${MARKS[l.status]} ${text.link(l.status)}`,
        tone: LINK_TONE[l.status],
      },
    })),
  ];
}

/**
 * The network map (Cytoscape.js, bundled at build time). Devices are nodes; each link is drawn in
 * its medium's color with the port at each end next to its own device.
 */
export function TopologyGraph(props: {
  nodes: MapNode[];
  links: MapLink[];
  roots: string[];
  selected: Selection;
  onSelect: (selection: Selection) => void;
  theme: string;
  label: string;
  deviceLabel: (n: MapNode) => string;
  linkLabel: (s: LinkStatus) => string;
}) {
  const { nodes, links, roots, selected, onSelect, theme, label, deviceLabel, linkLabel } = props;
  const host = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const select = useRef(onSelect);
  useEffect(() => {
    select.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    const graph = cytoscape({
      container: host.current,
      style: stylesheet(host.current!),
      minZoom: 0.3,
      maxZoom: 2.5,
      wheelSensitivity: 0.3,
      boxSelectionEnabled: false,
    });
    graph.on("tap", "node", (e) => select.current({ kind: "node", id: idOf(e.target) }));
    graph.on("tap", "edge", (e) => select.current({ kind: "link", id: idOf(e.target) }));
    graph.on("tap", (e) => {
      if (e.target === graph) select.current(null);
    });
    cy.current = graph;
    // The panel changes width with the window and the side nav, so keep the whole map in view.
    const resize = new ResizeObserver(() => {
      graph.resize();
      graph.fit(undefined, 24);
    });
    resize.observe(host.current!);
    return () => {
      resize.disconnect();
      graph.destroy();
      cy.current = null;
    };
  }, []);

  // Redraw on new data, a filter change or a theme change (colors are read from the tokens).
  // One frame later: the shell sets the new theme on <html> after this child's effect runs.
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const graph = cy.current;
      if (!graph || !host.current) return;
      graph.style(stylesheet(host.current));
      graph.elements().remove();
      graph.add(elements(host.current, nodes, links, { device: deviceLabel, link: linkLabel }));
      graph
        .layout({ name: "breadthfirst", roots, directed: false, spacingFactor: 1.15, padding: 24 })
        .run();
      graph.fit(undefined, 24);
      if (selectedRef.current) graph.getElementById(selectedRef.current.id).select();
    });
    return () => cancelAnimationFrame(frame);
  }, [nodes, links, roots, theme, deviceLabel, linkLabel]);

  const selectedRef = useRef(selected);
  useEffect(() => {
    selectedRef.current = selected;
    const graph = cy.current;
    if (!graph) return;
    graph.elements().unselect();
    if (selected) graph.getElementById(selected.id).select();
  }, [selected]);

  return <div ref={host} className="mapper__graph" role="img" aria-label={label} />;
}

function idOf(target: { id(): string } | Core): string {
  return "id" in target ? target.id() : "";
}
