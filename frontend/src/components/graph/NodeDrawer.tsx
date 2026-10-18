import { X } from "lucide-react";
import { api, GraphEdge, Observation } from "../../api";
import { fmtValue } from "../../lib/format";
import { useAsync } from "../../lib/useAsync";
import type { WorkspaceData } from "../../pages/IncidentWorkspace";
import { Badge, Disclosure, Empty, ErrorNotice, Loading } from "../ui";

const PROVENANCE: Record<string, string> = {
  architecture: "Architecture manifest",
  trace: "Observed in traces",
};

export default function NodeDrawer({ service, data, onClose, onSelect }: {
  service: string; data: WorkspaceData; onClose: () => void; onSelect: (s: string) => void;
}) {
  const { inc, graph, report } = data;
  const node = graph.nodes.find((n) => n.name === service);
  const obs = inc.observations.filter((o) => (o.linked_service ?? o.service) === service).sort((a, b) => b.score - a.score);
  const anomalous = obs.filter((o) => o.anomalous);
  const out = graph.edges.filter((e) => e.source === service);
  const inn = graph.edges.filter((e) => e.target === service);
  const hyp = report?.hypotheses.find((h) => h.service === service);
  const candidate = report && report.conclusion !== "inconclusive" ? report.suspected_root_cause : null;
  const explainedBy = report?.hypotheses[0]?.explained_services.includes(service) ? report.hypotheses[0].service : null;
  const blast = useAsync(() => api.blastRadius(service, inc.id), [service, inc.id]);

  return (
    <aside className="drawer" aria-label={`Service ${service}`}>
      <header className="drawer-head">
        <div>
          <h3>{service}</h3>
          <div className="drawer-sub">{[node?.kind, node?.language].filter(Boolean).join(" · ")}</div>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close details" title="Close"><X size={15} /></button>
      </header>
      <div className="drawer-body">
        <div className="badges">
          {service === candidate && <Badge tone="candidate">Root cause candidate</Badge>}
          {node?.anomalous ? <Badge tone="bad">Anomalous</Badge>
            : obs.length ? <Badge title="Telemetry exists for this service but none of it is anomalous">No anomaly detected</Badge>
            : <Badge title="No telemetry for this service in this incident; health is unknown">Unknown</Badge>}
          {hyp && <Badge>Hypothesis #{hyp.rank} · {hyp.fault_class}</Badge>}
          {explainedBy && explainedBy !== service && <Badge title="Symptom explained by a dependency path to the top hypothesis">Explained by {explainedBy}</Badge>}
        </div>

        <div className="drawer-section">
          <h4>Observations <span className="muted">{anomalous.length} anomalous / {obs.length}</span></h4>
          {obs.length === 0 ? <Empty>No telemetry linked to this service for this incident.</Empty> : (
            <ObservationTable obs={anomalous.length ? anomalous : obs} />
          )}
          {anomalous.length > 0 && obs.length > anomalous.length && (
            <Disclosure title={`Non-anomalous signals (${obs.length - anomalous.length})`}>
              <ObservationTable obs={obs.filter((o) => !o.anomalous)} />
            </Disclosure>
          )}
          {obs.some((o) => o.samples?.length) && (
            <Disclosure title="Log samples">
              {obs.filter((o) => o.samples?.length).map((o) => (
                <div key={o.id} className="log-samples">
                  <div className="muted">{o.signal}</div>
                  {o.samples.map((s, i) => <code key={i}>{s}</code>)}
                </div>
              ))}
            </Disclosure>
          )}
        </div>

        <div className="drawer-section">
          <h4>Depends on</h4>
          <EdgeList edges={out} side="target" onSelect={onSelect} />
          <h4>Called by</h4>
          <EdgeList edges={inn} side="source" onSelect={onSelect} />
        </div>

        <div className="drawer-section">
          <h4>If {service} fails</h4>
          {blast.error ? <ErrorNotice error={blast.error} /> : !blast.data ? <Loading /> : blast.data.entries.length === 0 ? (
            <Empty>No upstream services depend on it.</Empty>
          ) : (
            <>
              <div className="muted small">{blast.data.potential.length} upstream services could be affected · {blast.data.observed.length} show anomalies now</div>
              <ul className="chips">
                {[...blast.data.entries].sort((a, b) => a.depth - b.depth).map((e) => (
                  <li key={e.service}>
                    <button className={`chip${e.observed_impact ? " chip-anom" : ""}`} onClick={() => onSelect(e.service)} title={`${e.depth} hop(s)${e.observed_impact ? " · anomalous in this incident" : ""}`}>
                      {e.service}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}

export function ObservationTable({ obs }: { obs: Observation[] }) {
  return (
    <table className="tbl compact">
      <thead><tr><th>Signal</th><th>Type</th><th className="num" title="Robust z-score vs pre-incident baseline">Score</th><th>Baseline → observed</th></tr></thead>
      <tbody>
        {obs.map((o) => (
          <tr key={o.id}>
            <td>{o.caller ? <span className="muted">{o.caller} → </span> : null}{o.signal} <span className={o.direction === "up" ? "tone-anom" : "tone-impact"}>{o.direction === "up" ? "↑" : "↓"}</span></td>
            <td className="muted">{o.kind}</td>
            <td className="num">{o.score.toFixed(1)}</td>
            <td className="mono muted">{o.baseline == null && o.observed == null ? "—" : `${fmtValue(o.baseline)} → ${fmtValue(o.observed)}`}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function EdgeList({ edges, side, onSelect }: { edges: GraphEdge[]; side: "source" | "target"; onSelect: (s: string) => void }) {
  if (!edges.length) return <div className="muted small">None</div>;
  // Merge DEPENDS_ON and CALLS between the same pair into one row.
  const by = new Map<string, GraphEdge[]>();
  edges.forEach((e) => by.set(e[side], [...(by.get(e[side]) ?? []), e]));
  return (
    <ul className="chips">
      {[...by.entries()].sort().map(([svc, es]) => (
        <li key={svc}>
          <button className="chip" onClick={() => onSelect(svc)} title={es.map((e) => `${e.type} · ${PROVENANCE[e.provenance] ?? e.provenance}`).join("\n")}>
            {svc}{es.some((e) => e.type === "CALLS") && <span className="chip-tag">trace</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}

export function EdgeDrawer({ edge, onClose }: { edge: GraphEdge; onClose: () => void }) {
  return (
    <aside className="drawer" aria-label="Relationship">
      <header className="drawer-head">
        <div>
          <h3>{edge.source} → {edge.target}</h3>
          <div className="drawer-sub">{edge.type}</div>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close details" title="Close"><X size={15} /></button>
      </header>
      <div className="drawer-body">
        <dl className="kv">
          <dt>Source</dt><dd>{PROVENANCE[edge.provenance] ?? edge.provenance}</dd>
          {edge.evidence && (<><dt>Evidence</dt><dd>{edge.evidence}</dd></>)}
          {edge.observed_in != null && (<><dt>Observed in</dt><dd>{edge.observed_in} incident{edge.observed_in === 1 ? "" : "s"}</dd></>)}
        </dl>
        <p className="hint">
          {edge.type === "DEPENDS_ON" ? `${edge.source} is configured to call ${edge.target}; a failure in ${edge.target} can surface in ${edge.source}.`
            : `Parent/child spans show ${edge.source} calling ${edge.target}.`}
        </p>
      </div>
    </aside>
  );
}
