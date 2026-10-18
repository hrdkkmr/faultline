import cytoscape, { Core, ElementDefinition, Stylesheet } from "cytoscape";
import { Box, Database, Globe, LucideIcon, Maximize, RotateCcw, Search, Server, ZoomIn, ZoomOut } from "lucide-react";
import { createElement, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { GraphEdge, IncidentGraph } from "../../api";
import { shortService } from "../../lib/format";
import { IconButton } from "../ui";
import { prefersReducedMotion } from "../../lib/router";
import { layered } from "./layout";

export interface NodeStates {
  candidate: string | null;
  potential: Set<string>;
  pathEdges: Set<string>; // "source>target"
}

interface Props {
  graph: IncidentGraph;
  states: NodeStates;
  showTrace: boolean;
  highlightPaths: boolean;
  focusImpact: boolean;
  selected: string | null;
  onSelectNode: (name: string | null) => void;
  onSelectEdge: (e: GraphEdge) => void;
}

// Graph palette mirrors the CSS tokens in styles.css (Cytoscape cannot read CSS variables).
const C = {
  surface: "#1e1e1e", border: "#2c2c2c", text: "#ebebeb", muted: "#8a8a8a",
  anom: "#ff6b6b", anomBg: "#2a1414", cand: "#f2b544", candBg: "#2a2109", impact: "#a8a8a8",
  dep: "#3d3d3d", trace: "#6f9a52", accent: "#8dd950",
};

// Poppins 13px averages ~8px per character; 54px covers the icon and padding.
const nodeWidth = (name: string) => Math.max(112, shortService(name).length * 8.2 + 54);

const ICON: Record<string, LucideIcon> = { entrypoint: Globe, datastore: Database, service: Server };
const iconCache = new Map<string, string>();
function iconUri(kind: string, color: string) {
  const key = `${kind}:${color}`;
  let uri = iconCache.get(key);
  if (!uri) {
    const svg = renderToStaticMarkup(createElement(ICON[kind] ?? Box, { size: 16, color, strokeWidth: 2 }));
    uri = `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
    iconCache.set(key, uri);
  }
  return uri;
}

// Typed loosely: @types/cytoscape predates the underlay-* properties that cytoscape 3.30 supports.
const STYLE = [
  { selector: "node", style: {
    shape: "round-rectangle", "corner-radius": 10, width: "data(w)", height: 38, "background-color": C.surface, "border-width": 1.5,
    "border-color": C.border, label: "data(label)", color: C.text, "font-size": 13, "font-family": "Poppins, Segoe UI, system-ui, sans-serif", "font-weight": 500,
    "text-valign": "center", "text-halign": "center", "text-margin-x": 9, "text-wrap": "wrap", "line-height": 1.25,
    "background-image": "data(icon)", "background-width": 15, "background-height": 15, "background-position-x": 13,
    "background-position-y": "50%", "background-clip": "none", "transition-property": "opacity", "transition-duration": prefersReducedMotion() ? 0 : 150,
  } },
  { selector: "node.anom", style: { "border-color": C.anom, "background-color": C.anomBg, "border-width": 2 } },
  { selector: "node.potential", style: { "border-color": C.impact, "border-style": "dashed" } },
  { selector: "node.candidate", style: {
    "border-color": C.cand, "background-color": C.candBg, "border-width": 2.5, "border-style": "dashed", height: 50, "font-size": 13,
  } },
  { selector: "node.sel", style: { "underlay-color": C.accent, "underlay-opacity": 0.28, "underlay-padding": 5, "underlay-shape": "round-rectangle" } },
  { selector: "node.dim", style: { opacity: 0.28 } },
  { selector: "edge", style: {
    width: 1.4, "curve-style": "bezier", "control-point-step-size": 22, "target-arrow-shape": "triangle", "arrow-scale": 0.85,
    "line-color": C.dep, "target-arrow-color": C.dep, "transition-property": "opacity", "transition-duration": prefersReducedMotion() ? 0 : 150,
  } },
  { selector: "edge.calls", style: { "line-color": C.trace, "target-arrow-color": C.trace, "line-style": "dashed", "line-dash-pattern": [5, 4], width: 1.2 } },
  { selector: "edge.onpath", style: { "line-color": C.cand, "target-arrow-color": C.cand, width: 2.6, "z-index": 10 } },
  { selector: "edge.dim", style: { opacity: 0.12 } },
  { selector: "edge.hidden", style: { display: "none" } },
  { selector: "edge:selected", style: { "underlay-color": C.accent, "underlay-opacity": 0.35, "underlay-padding": 4 } },
] as unknown as Stylesheet[];

export default function ServiceGraph({ graph, states, showTrace, highlightPaths, focusImpact, selected, onSelectNode, onSelectEdge }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const handlers = useRef({ onSelectNode, onSelectEdge });
  handlers.current = { onSelectNode, onSelectEdge };
  const [q, setQ] = useState("");
  const positions = useMemo(() => layered(graph.nodes, graph.edges), [graph]);

  // Build the graph once per payload; state changes below only toggle classes (pan/zoom/drag survive).
  useEffect(() => {
    if (!el.current) return;
    const elements: ElementDefinition[] = [
      ...graph.nodes.map((n) => ({ data: { id: n.name, kind: n.kind, w: nodeWidth(n.name), w0: nodeWidth(n.name) }, position: { ...positions[n.name] } })),
      ...graph.edges.map((e) => ({
        data: { id: `${e.type}:${e.source}>${e.target}`, source: e.source, target: e.target, edge: e },
        classes: e.type === "CALLS" ? "calls" : "depends",
      })),
    ];
    const c = cytoscape({
      container: el.current, elements, style: STYLE, layout: { name: "preset", fit: true, padding: 40 },
      minZoom: 0.3, maxZoom: 2.5, wheelSensitivity: 0.25, boxSelectionEnabled: false, autounselectify: false,
    });
    c.on("tap", "node", (ev) => handlers.current.onSelectNode(ev.target.id()));
    c.on("tap", "edge", (ev) => handlers.current.onSelectEdge(ev.target.data("edge")));
    c.on("tap", (ev) => { if (ev.target === c) handlers.current.onSelectNode(null); });
    c.on("mouseover", "node", (ev) => { el.current!.title = `${ev.target.id()} (${ev.target.data("kind")})`; el.current!.style.cursor = "pointer"; });
    c.on("mouseover", "edge", (ev) => {
      const e: GraphEdge = ev.target.data("edge");
      el.current!.title = `${e.source} → ${e.target}\n${e.type} · ${e.provenance}${e.observed_in ? ` · seen in ${e.observed_in} incidents` : ""}`;
      el.current!.style.cursor = "pointer";
    });
    c.on("mouseout", "node, edge", () => { el.current!.title = ""; el.current!.style.cursor = ""; });
    cy.current = c;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); c.destroy(); cy.current = null; };
  }, [graph, positions]);

  // Apply visual state.
  useEffect(() => {
    const c = cy.current;
    if (!c) return;
    const anomalous = new Set(graph.nodes.filter((n) => n.anomalous).map((n) => n.name));
    const involved = new Set([...anomalous, ...states.potential, ...(states.candidate ? [states.candidate] : [])]);
    c.batch(() => {
      c.nodes().forEach((n) => {
        const name = n.id();
        const isCand = name === states.candidate;
        const isAnom = anomalous.has(name);
        n.toggleClass("anom", isAnom && !isCand);
        n.toggleClass("potential", !isAnom && !isCand && states.potential.has(name));
        n.toggleClass("candidate", isCand);
        n.toggleClass("sel", name === selected);
        n.toggleClass("dim", focusImpact && involved.size > 0 && !involved.has(name));
        n.data("w", isCand ? Math.max(n.data("w0"), 196) : n.data("w0"));
        n.data("label", isCand ? `${shortService(name)}\nroot cause candidate` : shortService(name));
        n.data("icon", iconUri(n.data("kind"), isCand ? C.cand : isAnom ? C.anom : C.muted));
      });
      c.edges().forEach((e) => {
        const key = `${e.data("source")}>${e.data("target")}`;
        const onPath = highlightPaths && states.pathEdges.has(key) && !e.hasClass("calls");
        e.toggleClass("onpath", onPath);
        e.toggleClass("hidden", e.hasClass("calls") && !showTrace);
        e.toggleClass("dim", focusImpact && involved.size > 0 && !onPath &&
          !(involved.has(e.data("source")) && involved.has(e.data("target"))));
      });
    });
  }, [graph, states, showTrace, highlightPaths, focusImpact, selected]);

  const zoom = (f: number) => {
    const c = cy.current;
    if (!c) return;
    c.zoom({ level: c.zoom() * f, renderedPosition: { x: c.width() / 2, y: c.height() / 2 } });
  };
  const fit = () => cy.current?.animate({ fit: { eles: cy.current.elements(":visible"), padding: 40 }, duration: prefersReducedMotion() ? 0 : 200 });
  const reset = () => {
    const c = cy.current;
    if (!c) return;
    c.nodes().forEach((n) => { n.position({ ...positions[n.id()] }); });
    c.edges().unselect();
    onSelectNode(null);
    setQ("");
    c.fit(undefined, 40);
  };

  const matches = q.trim() ? graph.nodes.filter((n) => n.name.includes(q.trim().toLowerCase())).map((n) => n.name) : [];
  function locate(name: string) {
    const c = cy.current;
    if (!c) return;
    onSelectNode(name);
    c.animate({ center: { eles: c.getElementById(name) }, zoom: Math.max(c.zoom(), 1), duration: prefersReducedMotion() ? 0 : 200 });
    setQ("");
  }
  function onSearchKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && matches[0]) locate(matches[0]);
    if (e.key === "Escape") setQ("");
  }

  return (
    <div className="graph-wrap">
      <div className="graph-canvas" ref={el} data-testid="graph" aria-label="Service dependency graph" role="application" />
      <div className="graph-search">
        <Search size={13} aria-hidden />
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onSearchKey} placeholder="Find service" aria-label="Find service in graph" />
        {matches.length > 0 && (
          <ul className="graph-search-results" role="listbox">
            {matches.slice(0, 8).map((m) => <li key={m}><button role="option" aria-selected={false} onClick={() => locate(m)}>{m}</button></li>)}
          </ul>
        )}
      </div>
      <div className="graph-controls" role="toolbar" aria-label="Graph controls">
        <IconButton label="Zoom in" onClick={() => zoom(1.25)}><ZoomIn size={15} /></IconButton>
        <IconButton label="Zoom out" onClick={() => zoom(0.8)}><ZoomOut size={15} /></IconButton>
        <IconButton label="Fit to view" onClick={fit}><Maximize size={15} /></IconButton>
        <IconButton label="Reset layout and selection" onClick={reset}><RotateCcw size={15} /></IconButton>
      </div>
    </div>
  );
}
