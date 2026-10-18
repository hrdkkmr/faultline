import cytoscape, { Core } from "cytoscape";
import { useEffect, useRef } from "react";
import { IncidentGraph } from "../api";

interface Props {
  graph: IncidentGraph;
  root?: string | null;
  explained?: string[];
  highlightPaths?: string[][];
  onSelect: (kind: "node" | "edge", data: Record<string, unknown>) => void;
}

// Layered layout: entrypoint at the top, datastores at the bottom (Online Boutique call depth).
const LAYER: Record<string, number> = {
  "frontend-external": 0, frontend: 1, checkoutservice: 2, recommendationservice: 2, adservice: 2,
  cartservice: 3, productcatalogservice: 3, currencyservice: 3, shippingservice: 3, paymentservice: 3,
  emailservice: 3, redis: 4,
};

export default function GraphView({ graph, root, explained = [], highlightPaths = [], onSelect }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);

  useEffect(() => {
    if (!el.current) return;
    const layerCount: Record<number, number> = {};
    const pos: Record<string, { x: number; y: number }> = {};
    const byLayer: Record<number, string[]> = {};
    graph.nodes.forEach((n) => {
      const l = LAYER[n.name] ?? 3;
      (byLayer[l] ||= []).push(n.name);
    });
    Object.entries(byLayer).forEach(([l, names]) => {
      names.sort().forEach((name, i) => {
        layerCount[+l] = names.length;
        pos[name] = { x: (i - (names.length - 1) / 2) * 150, y: +l * 120 };
      });
    });
    const pathEdges = new Set<string>();
    highlightPaths.forEach((p) => p.slice(1).forEach((b, i) => pathEdges.add(`${p[i]}>${b}`)));

    const elements = [
      ...graph.nodes.map((n) => ({
        data: { id: n.name, label: n.name.replace("service", ""), ...n },
        position: pos[n.name],
        classes: [n.anomalous ? "anom" : "", n.name === root ? "root" : "", explained.includes(n.name) ? "explained" : ""].join(" "),
      })),
      ...graph.edges.map((e) => ({
        data: { id: `${e.type}:${e.source}>${e.target}`, ...e },
        classes: [e.type === "CALLS" ? "calls" : "depends", pathEdges.has(`${e.source}>${e.target}`) ? "onpath" : ""].join(" "),
      })),
    ];
    cy.current?.destroy();
    const c = cytoscape({
      container: el.current,
      elements,
      layout: { name: "preset", padding: 30 },
      userZoomingEnabled: false,
      boxSelectionEnabled: false,
      style: [
        { selector: "node", style: { label: "data(label)", "font-size": 11, color: "#cbd5e1", "text-valign": "bottom",
          "text-margin-y": 6, "background-color": "#334155", width: 28, height: 28, "border-width": 2, "border-color": "#475569" } },
        { selector: "node.anom", style: { "background-color": "#0ea5e9", "border-color": "#7dd3fc" } },
        { selector: "node.explained", style: { "border-color": "#fbbf24", "border-style": "dashed", "border-width": 3 } },
        { selector: "node.root", style: { "background-color": "#f59e0b", "border-color": "#fde68a", width: 40, height: 40, "border-width": 4 } },
        { selector: "edge", style: { width: 1.5, "curve-style": "bezier", "target-arrow-shape": "triangle", "arrow-scale": 0.8 } },
        { selector: "edge.depends", style: { "line-color": "#64748b", "target-arrow-color": "#64748b" } },
        { selector: "edge.calls", style: { "line-color": "#22c55e", "target-arrow-color": "#22c55e", "line-style": "dashed",
          "control-point-step-size": 25 } },
        { selector: "edge.onpath", style: { "line-color": "#f59e0b", "target-arrow-color": "#f59e0b", width: 3.5 } },
        { selector: ":selected", style: { "overlay-color": "#f8fafc", "overlay-opacity": 0.15 } },
      ],
    });
    c.on("tap", "node", (ev) => onSelect("node", ev.target.data()));
    c.on("tap", "edge", (ev) => onSelect("edge", ev.target.data()));
    cy.current = c;
    return () => c.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, root, explained.join(","), JSON.stringify(highlightPaths)]);

  return <div className="graph" ref={el} data-testid="graph" />;
}
