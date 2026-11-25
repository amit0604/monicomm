// Network graph: hosts are nodes, host pairs are edges (Cytoscape.js, bundled at build time).
// Colors come from the site's tokens so the graph follows light and dark themes.
import cytoscape from "cytoscape";
import { token } from "./ui.js";

const clamp = (value, lo, hi) => Math.max(lo, Math.min(hi, value));

function palette(root) {
  return {
    internal: token(root, "--chart-1"),
    external: token(root, "--chart-3"),
    suspicious: token(root, "--critical-strong"),
    hub: token(root, "--accent-pcap"),
    label: token(root, "--text-muted"),
    labelOutline: token(root, "--surface"),
    selected: token(root, "--primary"),
    edges: {
      TCP: token(root, "--chart-1"),
      UDP: token(root, "--chart-2"),
      ICMP: token(root, "--chart-5"),
      IP: token(root, "--chart-6"),
      Mixed: token(root, "--chart-4"),
    },
  };
}

function style(c) {
  return [
    {
      selector: "node",
      style: {
        "background-color": "data(color)",
        width: "data(size)",
        height: "data(size)",
        label: "data(id)",
        color: c.label,
        "font-family": '"Cascadia Mono", Consolas, "Liberation Mono", monospace',
        "font-size": 10,
        "text-valign": "bottom",
        "text-margin-y": 5,
        "text-outline-color": c.labelOutline,
        "text-outline-width": 2,
      },
    },
    { selector: "node[?hub]", style: { "border-width": 3, "border-color": c.hub } },
    {
      selector: "edge",
      style: {
        width: "data(width)",
        "line-color": "data(color)",
        opacity: 0.6,
        "curve-style": "bezier",
      },
    },
    {
      selector: "node:selected",
      style: { "border-width": 4, "border-color": c.selected, "font-weight": "bold" },
    },
    { selector: "edge:selected", style: { opacity: 1 } },
    { selector: ".faded", style: { opacity: 0.12 } },
    { selector: "edge.focus", style: { opacity: 0.95 } },
  ];
}

export function createGraph(container, { onNode, onEdge, onClear }) {
  let colors = palette(container);
  const cy = cytoscape({
    container,
    style: style(colors),
    minZoom: 0.15,
    maxZoom: 4,
    userZoomingEnabled: false,
    boxSelectionEnabled: false,
  });

  // Plain scrolling moves the page; Ctrl + scroll (or pinch) zooms the graph.
  container.addEventListener(
    "wheel",
    (event) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const rect = container.getBoundingClientRect();
      cy.zoom({
        level: cy.zoom() * Math.exp(-event.deltaY * 0.002),
        renderedPosition: { x: event.clientX - rect.left, y: event.clientY - rect.top },
      });
    },
    { passive: false },
  );

  cy.on("tap", "node", (event) => {
    focus(event.target);
    onNode(event.target.id());
  });
  cy.on("tap", "edge", (event) => {
    const edge = event.target;
    cy.elements().addClass("faded");
    edge.removeClass("faded").addClass("focus");
    edge.connectedNodes().removeClass("faded");
    onEdge(edge.data());
  });
  cy.on("tap", (event) => {
    if (event.target === cy) {
      clearFocus();
      onClear();
    }
  });

  function focus(node) {
    cy.elements().removeClass("focus").addClass("faded");
    node.closedNeighborhood().removeClass("faded");
    node.connectedEdges().addClass("focus");
  }
  function clearFocus() {
    cy.elements().removeClass("faded focus").unselect();
  }
  function layout() {
    cy.layout({
      name: "cose",
      animate: false,
      randomize: true,
      nodeRepulsion: () => 400000,
      idealEdgeLength: () => 140,
      edgeElasticity: () => 60,
      nodeOverlap: 20,
      gravity: 0.25,
      numIter: 1500,
      padding: 40,
    }).run();
    cy.fit(undefined, 40);
  }

  return {
    render({ nodes, edges }) {
      colors = palette(container); // pick up a theme switch
      cy.style(style(colors));
      cy.elements().remove();
      cy.add(
        nodes.map((n) => ({
          group: "nodes",
          data: {
            ...n,
            color: n.suspicious
              ? colors.suspicious
              : n.internal
                ? colors.internal
                : colors.external,
            size: clamp(14 + Math.log10(Math.max(n.bytes, 1)) * 6, 18, 60),
          },
        })),
      );
      cy.add(
        edges.map((e) => ({
          group: "edges",
          data: {
            ...e,
            id: `${e.source}|${e.target}`,
            color: colors.edges[e.protocol] || colors.edges.Mixed,
            width: clamp(1 + Math.log10(e.packets) * 1.8, 1, 8),
          },
        })),
      );
      layout();
    },
    relayout: layout,
    fit: () => cy.fit(undefined, 40),
    clear: clearFocus,
    select(ip) {
      const node = cy.getElementById(ip);
      if (!node.length) return false;
      cy.elements().unselect();
      node.select();
      focus(node);
      cy.animate({ center: { eles: node }, zoom: Math.max(cy.zoom(), 1.2) }, { duration: 300 });
      return true;
    },
    edgesOf: (ip) =>
      cy
        .getElementById(ip)
        .connectedEdges()
        .map((e) => e.data()),
    resize: () => cy.resize(),
    destroy: () => cy.destroy(),
  };
}
