import { useCallback, useEffect, useState } from "react";
import {
  api, EvidencePaths, IncidentGraph, IncidentView, InvestigationRow, Mitigation, Mode, ObservationRecord, Report, SimResult,
} from "../api";
import { Empty, ErrorBox, IdLink, Panel, pct, Tag } from "./common";
import GraphView from "./GraphView";

const MODES: { id: Mode; label: string }[] = [
  { id: "C_graph_memory", label: "C · graph + memory" },
  { id: "B_graph", label: "B · graph only" },
  { id: "A_incident_only", label: "A · incident only (baseline)" },
];

export default function IncidentPage({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [inc, setInc] = useState<IncidentView | null>(null);
  const [graph, setGraph] = useState<IncidentGraph | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [history, setHistory] = useState<InvestigationRow[]>([]);
  const [mode, setMode] = useState<Mode>("C_graph_memory");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selHyp, setSelHyp] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<EvidencePaths | null>(null);
  const [inspect, setInspect] = useState<{ title: string; body: unknown } | null>(null);
  const [sim, setSim] = useState<Record<string, SimResult | string>>({});
  const [approve, setApprove] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setError(null);
    setReport(null); setEvidence(null); setSelHyp(null); setInspect(null); setSim({});
    try {
      const [i, g, h] = await Promise.all([api.incident(id), api.graph(id), api.investigations(id)]);
      setInc(i); setGraph(g); setHistory(h);
      if (h.length) setReport(await api.investigation(h[0].id));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function run() {
    setBusy("Running graph investigation (Cypher traversal, memory retrieval, action checks)…");
    setError(null);
    try {
      const r = await api.investigate(id, mode);
      setReport(r);
      setHistory(await api.investigations(id));
      setInc(await api.incident(id));
      setEvidence(null); setSelHyp(null);
      onChanged();
    } catch (e) {
      setError(`Investigation failed: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  async function openEvidence(hid: string) {
    setSelHyp(hid);
    try { setEvidence(await api.evidence(hid)); } catch (e) { setError((e as Error).message); }
  }

  async function openObs(oid: string) {
    try {
      const r: ObservationRecord = await api.observation(oid);
      setInspect({ title: `Observation ${oid}`, body: r });
    } catch (e) {
      setInspect({ title: oid, body: `Not an observation record (${(e as Error).message}). Memory/deployment IDs are listed in the Memory view.` });
    }
  }

  async function simulate(m: Mitigation) {
    const key = `${m.action.type}:${m.action.target}`;
    setSim((s) => ({ ...s, [key]: "running…" }));
    try {
      const r = await api.simulate(id, m.action.type, m.action.target, !!approve[key]);
      setSim((s) => ({ ...s, [key]: r }));
      onChanged();
      setInc(await api.incident(id));
    } catch (e) {
      setSim((s) => ({ ...s, [key]: (e as Error).message }));
    }
  }

  if (error && !inc) return <ErrorBox error={error} />;
  if (!inc || !graph) return <div className="loading">Loading incident from FalkorDB…</div>;

  const top = report?.hypotheses[0];
  const hyp = report?.hypotheses.find((h) => h.id === selHyp) ?? top;
  const anomalous = inc.observations.filter((o) => o.anomalous).slice(0, 14);

  return (
    <div className="incident">
      <div className="incident-head">
        <div>
          <h2>{inc.title}</h2>
          <div className="meta">
            <code>{inc.id}</code> · {inc.detected_at_iso?.replace("T", " ").slice(0, 16)} UTC ·{" "}
            {inc.source === "synthetic" ? <Tag p="synthetic" /> : <Tag p="observed">RCAEval benchmark</Tag>} · status{" "}
            <b>{inc.status}</b> · telemetry: {Object.entries(inc.telemetry).filter(([, v]) => v).map(([k]) => k).join(", ")}
          </div>
          {inc.description && <p className="desc">{inc.description}</p>}
          <div className="prov">Provenance: {inc.provenance}</div>
        </div>
        <div className="run">
          <select value={mode} onChange={(e) => setMode(e.target.value as Mode)} aria-label="mode">
            {MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
          <button className="primary" onClick={run} disabled={!!busy}>{busy ? "Investigating…" : "Investigate"}</button>
        </div>
      </div>
      {busy && <div className="progress"><span className="spinner" /> {busy}</div>}
      <ErrorBox error={error} />

      <div className="grid2">
        <Panel title="Dependency graph" right={<span className="hint">grey = DEPENDS_ON (architecture) · green dashed = CALLS (trace-observed) · blue = anomalous · amber = hypothesis</span>}>
          <GraphView
            graph={graph}
            root={report?.suspected_root_cause ?? top?.service}
            explained={hyp?.explained_services}
            highlightPaths={(evidence?.symptom_paths ?? hyp?.graph_paths ?? []).map((p) => p.path)}
            onSelect={(kind, d) => setInspect({ title: kind === "node" ? `Service ${d.name}` : `Edge ${d.type} ${d.source} → ${d.target}`, body: d })}
          />
        </Panel>
        <Panel title="Observed anomalies" right={<Tag p="observed" />}>
          {anomalous.length === 0 ? <Empty>No anomalous observations.</Empty> : (
            <table className="tbl">
              <thead><tr><th>service</th><th>signal</th><th>z</th><th>baseline → observed</th></tr></thead>
              <tbody>
                {anomalous.map((o) => (
                  <tr key={o.id} onClick={() => openObs(o.id)} className="clickable">
                    <td>{o.caller ? `${o.caller} → ` : ""}{o.service}</td>
                    <td>{o.signal} {o.direction === "up" ? "▲" : "▼"}</td>
                    <td>{o.score.toFixed(0)}</td>
                    <td className="mono">{fmt(o.baseline)} → {fmt(o.observed)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      {!report ? (
        <Empty>No investigation yet. Choose a mode and press <b>Investigate</b>.</Empty>
      ) : (
        <>
          <div className={`verdict ${report.conclusion}`}>
            {report.conclusion === "inconclusive" ? (
              <><b>Inconclusive</b> — gather more evidence. {report.missing_information.join("; ")}</>
            ) : (
              <>
                <Tag p="hypothesis" /> Suspected root cause <b>{report.suspected_root_cause}</b> ({report.suspected_fault_class}) ·
                score share {pct(report.confidence)} · mode <code>{report.mode}</code> · {report.elapsed_ms.toFixed(0)} ms ·{" "}
                {report.tool_calls.length} tool calls
              </>
            )}
          </div>

          <div className="grid3">
            <Panel title="Root-cause hypotheses" right={<Tag p="hypothesis" />}>
              {report.hypotheses.map((h) => (
                <div key={h.id} className={`hyp ${h.id === (selHyp ?? top?.id) ? "sel" : ""}`} onClick={() => openEvidence(h.id)}>
                  <div className="hyp-head">
                    <b>#{h.rank} {h.service}</b> <span className="pill">{h.fault_class}</span>
                    <span className="score">{h.score.total.toFixed(2)}</span>
                  </div>
                  <div className="bars">
                    <Bar label="local" v={h.score.local_evidence} /> <Bar label="coverage" v={h.score.coverage} />
                    {h.score.memory > 0 && <Bar label="memory" v={h.score.memory} />}
                  </div>
                  <ul className="small">{h.rationale.map((r, i) => <li key={i}>{r}</li>)}</ul>
                </div>
              ))}
            </Panel>

            <Panel title="Evidence & relationship paths" right={hyp && <span className="hint">{hyp.service}</span>}>
              {!evidence ? (
                hyp ? (
                  <>
                    <p className="small">Click a hypothesis to load its stored evidence from the graph.</p>
                    <h4>Supporting</h4>
                    {hyp.supporting_evidence.map((x) => <div key={x}><IdLink id={x} onOpen={openObs} /></div>)}
                  </>
                ) : <Empty>No hypotheses.</Empty>
              ) : (
                <>
                  <h4>Supporting <Tag p="observed" /></h4>
                  {evidence.supporting.map((s) => (
                    <div key={s.observation} className="ev"><IdLink id={s.observation} onOpen={openObs} /> <span>{s.signal} z={s.score.toFixed(0)}</span></div>
                  ))}
                  <h4>Contradicting</h4>
                  {evidence.contradicting.length ? evidence.contradicting.map((s) => (
                    <div key={s.observation} className="ev"><IdLink id={s.observation} onOpen={openObs} /> <span>{s.signal} z={s.score?.toFixed(1)}</span></div>
                  )) : <div className="small">none recorded</div>}
                  <h4>Symptom → hypothesis paths</h4>
                  {evidence.symptom_paths.length ? evidence.symptom_paths.map((p) => (
                    <div key={p.service} className="path">
                      {p.path.join(" → ")}{" "}
                      {[...new Set(p.rel_sources)].map((s) => <Tag key={String(s)} p={s === "trace" ? "trace" : "architecture"} />)}
                    </div>
                  )) : <div className="small">no dependency path from other anomalous services</div>}
                  {evidence.memories.length > 0 && (<><h4>Informed by</h4>{evidence.memories.map((m) => <div key={m.memory}><Tag p="memory">{m.memory}</Tag></div>)}</>)}
                </>
              )}
            </Panel>

            <Panel title="Blast radius" right={<Tag p="architecture" />}>
              {report.affected_services.potential ? (
                <>
                  <div className="small">{report.affected_services.basis}</div>
                  <h4>Observed impact ({report.affected_services.observed?.length ?? 0})</h4>
                  <div className="chips">{report.affected_services.observed?.map((s) => <span key={s} className="chip anom">{s}</span>)}</div>
                  <h4>Potential impact ({report.affected_services.potential.length})</h4>
                  <div className="chips">{report.affected_services.potential.map((s) => <span key={s} className="chip">{s}</span>)}</div>
                </>
              ) : <Empty>Not computed in this mode.</Empty>}
              <h4>Recent changes</h4>
              {report.recent_changes.changes?.length ? report.recent_changes.changes.map((c) => (
                <div key={c.id} className="small"><Tag p="synthetic" /> {c.id} on {c.service} ({c.version})</div>
              )) : <div className="small">{report.recent_changes.note ?? "none in the hour before detection"}</div>}
            </Panel>
          </div>

          <div className="grid2">
            <Panel title="Candidate mitigations & risk" right={<span className="hint">actions run ONLY in the simulator</span>}>
              <table className="tbl">
                <thead><tr><th>action</th><th>verdict</th><th>risk</th><th>why / blockers</th><th>simulate</th></tr></thead>
                <tbody>
                  {report.candidate_mitigations.slice(0, 10).map((m) => {
                    const key = `${m.action.type}:${m.action.target}`;
                    const res = sim[key];
                    return (
                      <tr key={key} className={m.verdict}>
                        <td><b>{m.action.type}</b> {m.action.target && <>on {m.action.target}</>}</td>
                        <td><span className={`pill v-${m.verdict}`}>{m.verdict.replace("_", " ")}</span>
                          {m.memory_effect !== 0 && <div className="small">memory {m.memory_effect > 0 ? "+" : ""}{m.memory_effect.toFixed(2)}</div>}</td>
                        <td>{m.risk}{m.requires_approval && <div className="small">needs approval</div>}</td>
                        <td className="small">{[...m.preconditions_met, ...m.blockers.map((b) => `✗ ${b}`)].map((t, i) => <div key={i}>{t}</div>)}</td>
                        <td>
                          {m.action.type !== "gather_more_evidence" && (
                            <>
                              {m.requires_approval && (
                                <label className="small"><input type="checkbox" checked={!!approve[key]}
                                  onChange={(e) => setApprove((a) => ({ ...a, [key]: e.target.checked }))} /> approve</label>
                              )}
                              <button onClick={() => simulate(m)}>Simulate</button>
                              {res && (typeof res === "string" ? <div className="small err">{res}</div> : (
                                <div className={`small outcome ${res.outcome.result}`}>
                                  <Tag p="simulated" /> {res.outcome.result}{res.duplicate ? " (already recorded)" : ""}
                                  {res.outcome.side_effects.map((s) => <div key={s}>⚠ {s}</div>)}
                                  <div>→ <Tag p="memory">{res.memory_id}</Tag></div>
                                </div>
                              ))}
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Panel>

            <Panel title="Historical memory considered" right={<Tag p="memory" />}>
              {report.memories_considered.length === 0 ? (
                <Empty>{report.mode === "C_graph_memory" ? "No related memories in the graph yet." : "Memory not used in this mode."}</Empty>
              ) : report.memories_considered.map((m) => (
                <div key={m.memory_id} className={`mem ${m.verdict}`}>
                  <div><span className={`pill m-${m.verdict}`}>{m.verdict}</span> <b>{m.action_type}</b> on {m.service} →{" "}
                    <b className={m.outcome}>{m.outcome}</b> <span className="small">(from {m.derived_from}, coverage {pct(m.coverage)}, similarity {pct(m.source_similarity)})</span></div>
                  <div className="small">{m.lesson}</div>
                  {m.reasons.map((r) => <div key={r} className="small reason">• {r}</div>)}
                </div>
              ))}
              <h4>Related incidents</h4>
              {report.related_incidents.length ? report.related_incidents.map((r) => (
                <div key={r.incident_id} className="small"><code>{r.incident_id}</code> Jaccard {r.jaccard.toFixed(2)} · shared {r.shared.slice(0, 3).join(", ")}</div>
              )) : <div className="small">none</div>}
            </Panel>
          </div>

          <div className="grid2">
            <Panel title="Narrative" right={<span className="hint">{report.narrative_source}</span>}>
              <pre className="narrative">{report.narrative}</pre>
              {report.missing_information.length > 0 && (
                <><h4>Missing information</h4><ul className="small">{report.missing_information.map((m) => <li key={m}>{m}</li>)}</ul></>
              )}
            </Panel>
            <Panel title="Investigation history">
              {history.length === 0 ? <Empty>No stored investigations.</Empty> : (
                <table className="tbl">
                  <thead><tr><th>when</th><th>mode</th><th>result</th></tr></thead>
                  <tbody>{history.map((h) => (
                    <tr key={h.id} className="clickable" onClick={async () => setReport(await api.investigation(h.id))}>
                      <td>{h.created_at.replace("T", " ").slice(0, 19)}</td><td>{h.mode}</td>
                      <td>{h.conclusion === "inconclusive" ? "inconclusive" : `${h.top_service} (${pct(h.confidence)})`}</td>
                    </tr>))}</tbody>
                </table>
              )}
              <h4>Tool calls (latest run)</h4>
              <div className="small mono">{report.tool_calls.map((t, i) => <div key={i}>{t.tool} · {t.results} rows · {t.ms} ms</div>)}</div>
            </Panel>
          </div>
        </>
      )}

      {inspect && (
        <div className="drawer" role="dialog">
          <header><b>{inspect.title}</b><button onClick={() => setInspect(null)}>✕</button></header>
          <pre>{typeof inspect.body === "string" ? inspect.body : JSON.stringify(inspect.body, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

function Bar({ label, v }: { label: string; v: number }) {
  return <span className="bar" title={`${label} ${v.toFixed(2)}`}><i style={{ width: `${Math.min(100, v * 100)}%` }} />{label}</span>;
}

const fmt = (v: number | null) => (v == null ? "—" : Math.abs(v) >= 1000 ? v.toExponential(2) : +v.toFixed(3));
