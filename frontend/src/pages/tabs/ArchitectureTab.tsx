import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { useMemo, useState } from "react";
import type { GraphEdge, Observation } from "../../api";
import NodeDrawer, { EdgeDrawer } from "../../components/graph/NodeDrawer";
import ServiceGraph, { NodeStates } from "../../components/graph/ServiceGraph";
import { Empty, IconButton } from "../../components/ui";
import { fmtValue } from "../../lib/format";
import type { WorkspaceData } from "../IncidentWorkspace";

export default function ArchitectureTab({ data }: { data: WorkspaceData }) {
  const { inc, graph, report } = data;
  const [selected, setSelected] = useState<string | null>(null);
  const [edge, setEdge] = useState<GraphEdge | null>(null);
  const [showTrace, setShowTrace] = useState(true);
  const [paths, setPaths] = useState(true);
  const [focus, setFocus] = useState(false);
  // On narrow screens the panel overlays the graph, so start with it closed there.
  const [panelOpen, setPanelOpen] = useState(() => window.innerWidth > 1100);

  const candidate = report && report.conclusion !== "inconclusive" ? report.suspected_root_cause : null;
  const top = report?.hypotheses[0];
  const states: NodeStates = useMemo(() => ({
    candidate,
    potential: new Set(report?.affected_services.potential ?? []),
    pathEdges: new Set((candidate ? top?.graph_paths ?? [] : []).flatMap((p) => p.path.slice(1).map((b, i) => `${p.path[i]}>${b}`))),
  }), [report, candidate, top]);

  const anomalies = useMemo(() => {
    const by = new Map<string, Observation[]>();
    inc.observations.filter((o) => o.anomalous).forEach((o) => {
      const s = o.linked_service ?? o.service;
      by.set(s, [...(by.get(s) ?? []), o]);
    });
    return [...by.entries()]
      .map(([service, obs]) => ({ service, obs: obs.sort((a, b) => b.score - a.score), max: Math.max(...obs.map((o) => o.score)) }))
      .sort((a, b) => b.max - a.max);
  }, [inc]);

  const hasTrace = graph.edges.some((e) => e.type === "CALLS");
  const affected = report?.affected_services;
  const entries = [...(affected?.entries ?? [])].sort((a, b) => a.depth - b.depth || a.service.localeCompare(b.service));
  const selectNode = (n: string | null) => { setSelected(n); setEdge(null); };
  const drawerOpen = !!selected || !!edge;

  return (
    <div className="arch">
      <div className="arch-toolbar">
        <div className="toggles" role="group" aria-label="Graph display">
          <Toggle checked={paths} onChange={setPaths} disabled={!states.pathEdges.size} label="Impact paths"
            title={states.pathEdges.size ? "Highlight dependency paths from symptoms to the root cause candidate" : "Run an investigation to compute impact paths"} />
          <Toggle checked={focus} onChange={setFocus} label="Focus impacted" title="Dim services with no observed or potential impact" />
          {hasTrace && <Toggle checked={showTrace} onChange={setShowTrace} label="Trace calls" title="Show CALLS edges observed in benchmark traces" />}
        </div>
        <div className="legend" aria-label="Legend">
          <span><i className="lg lg-anom" />Anomalous</span>
          {candidate && <span><i className="lg lg-cand" />Candidate</span>}
          {states.potential.size > 0 && <span><i className="lg lg-impact" />Potential impact</span>}
          <span><i className="lg-line" />Depends on</span>
          {hasTrace && showTrace && <span><i className="lg-line lg-trace" />Trace call</span>}
        </div>
        <IconButton label={panelOpen ? "Hide impact panel" : "Show impact panel"} onClick={() => setPanelOpen((o) => !o)}>
          {panelOpen ? <PanelRightClose size={15} /> : <PanelRightOpen size={15} />}
        </IconButton>
      </div>

      <div className={`arch-body ${panelOpen || drawerOpen ? "with-panel" : ""}`}>
        <ServiceGraph graph={graph} states={states} showTrace={showTrace} highlightPaths={paths} focusImpact={focus}
          selected={selected} onSelectNode={selectNode} onSelectEdge={(e) => { setEdge(e); setSelected(null); }} />

        {selected ? (
          <NodeDrawer service={selected} data={data} onClose={() => setSelected(null)} onSelect={selectNode} />
        ) : edge ? (
          <EdgeDrawer edge={edge} onClose={() => setEdge(null)} />
        ) : panelOpen && (
          <aside className="side-panel" aria-label="Impact summary">
            {!report ? (
              <p className="hint">Run an investigation to compute the blast radius.</p>
            ) : !affected?.potential ? (
              <p className="hint">Not computed in baseline mode.</p>
            ) : entries.length > 0 && (
              <div className="side-block">
                <h4>Blast radius from {affected.root}</h4>
                <ul className="rows">
                  {entries.map((e) => (
                    <li key={e.service}>
                      <button className="row-btn" onClick={() => selectNode(e.service)}>
                        <span className="row-main">{e.service}</span>
                        <span className="row-meta" title="Dependency hops from the root cause candidate">{e.depth} hop{e.depth > 1 ? "s" : ""}</span>
                        {e.observed_impact ? <span className="tone-anom row-meta">observed</span> : <span className="row-meta">potential</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="side-block">
              <h4>Observed anomalies</h4>
              {anomalies.length === 0 ? <Empty>No anomalous observations.</Empty> : (
                <ul className="rows">
                  {anomalies.map((a) => (
                    <li key={a.service}>
                      <button className="row-btn" onClick={() => selectNode(a.service)}>
                        <span className="row-main">{a.service}</span>
                        <span className="row-meta">{a.obs.length} signal{a.obs.length > 1 ? "s" : ""}</span>
                      </button>
                      <div className="sig-list">
                        {a.obs.slice(0, 3).map((o) => (
                          <span key={o.id} className="sig" title={`${o.kind} · baseline ${fmtValue(o.baseline)} → observed ${fmtValue(o.observed)}`}>
                            {o.caller ? `${o.caller}→` : ""}{o.signal} {o.direction === "up" ? "↑" : "↓"} <b>{o.score.toFixed(0)}</b>
                          </span>
                        ))}
                        {a.obs.length > 3 && <span className="sig muted">+{a.obs.length - 3}</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {anomalies.length > 0 && <p className="hint" title="Robust z-score against the pre-incident baseline">Number = anomaly score (robust z)</p>}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

function Toggle({ checked, onChange, label, title, disabled }: {
  checked: boolean; onChange: (v: boolean) => void; label: string; title?: string; disabled?: boolean;
}) {
  return (
    <label className={`toggle${disabled ? " disabled" : ""}`} title={title}>
      <input type="checkbox" checked={checked && !disabled} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle-track" aria-hidden />
      {label}
    </label>
  );
}
