import { ArrowRight, Play } from "lucide-react";
import { useState } from "react";
import { api, DepPath, Hypothesis } from "../../api";
import { Badge, Disclosure, Empty, ErrorNotice, Loading, ScoreBar, Section, Spinner } from "../../components/ui";
import { whenEpoch } from "../../lib/format";
import { useAsync } from "../../lib/useAsync";
import type { WorkspaceData } from "../IncidentWorkspace";

export default function EvidenceTab({ data, onInvestigate, running }: { data: WorkspaceData; onInvestigate: () => void; running: boolean }) {
  const { report } = data;
  const [sel, setSel] = useState<string | null>(null);

  if (!report) {
    return (
      <div className="tab-empty">
        <p>No investigation for this incident yet.</p>
        <button className="btn-primary" onClick={onInvestigate} disabled={running}>{running ? <Spinner /> : <Play size={14} />} Investigate</button>
      </div>
    );
  }

  const hyps = report.hypotheses;
  const hyp = hyps.find((h) => h.id === sel) ?? hyps[0];
  const maxTotal = Math.max(...hyps.map((h) => h.score.total), 1);
  const changes = report.recent_changes.changes ?? [];

  return (
    <div className="evidence">
      {report.conclusion === "inconclusive" && (
        <div className="notice notice-warn">Inconclusive: no hypothesis has enough local evidence to rank as a root cause.</div>
      )}
      {report.missing_information.length > 0 && (
        <div className="data-gaps"><span className="muted">Data gaps</span>{report.missing_information.map((m) => <span key={m} className="gap">{m}</span>)}</div>
      )}

      <div className="evidence-grid">
        <Section title="Hypotheses" className="hyp-list">
          {hyps.length === 0 ? <Empty>No hypotheses were generated.</Empty> : (
            <ol className="hyp-rows">
              {hyps.map((h) => (
                <li key={h.id}>
                  <button className={`hyp-row${h.id === hyp?.id ? " selected" : ""}`} onClick={() => setSel(h.id)} aria-pressed={h.id === hyp?.id}>
                    <span className="hyp-rank">#{h.rank}</span>
                    <span className="hyp-svc">{h.service}</span>
                    <span className="hyp-class muted">{h.fault_class}</span>
                    <span className="hyp-score" title="Ranking score (local evidence + graph coverage + memory)">
                      <span className="mini-track"><i style={{ width: `${(h.score.total / maxTotal) * 100}%` }} /></span>
                      {h.score.total.toFixed(2)}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </Section>

        {hyp && <HypothesisDetail hyp={hyp} isTop={hyp.id === hyps[0]?.id && report.conclusion !== "inconclusive"} />}
      </div>

      <div className="evidence-extra">
        <Disclosure title="Recent changes" meta={changes.length ? `${changes.length}` : report.recent_changes.data_available === false ? "no data" : "none"}>
          {changes.length ? (
            <table className="tbl compact">
              <thead><tr><th>Change</th><th>Service</th><th>Version</th><th>When</th></tr></thead>
              <tbody>{changes.map((c) => (
                <tr key={c.id}><td className="mono">{c.id}</td><td>{c.service}</td>
                  <td className="mono">{c.previous_version ? `${c.previous_version} → ` : ""}{c.version ?? "—"}</td><td>{whenEpoch(c.at)}</td></tr>
              ))}</tbody>
            </table>
          ) : <p className="muted small">{report.recent_changes.note ?? "No deployments recorded in the hour before detection."}</p>}
        </Disclosure>
        {report.narrative && (
          <Disclosure title="Narrative" meta={report.narrative_source === "deterministic" ? "Deterministic" : report.narrative_source}>
            <p className="narrative">{report.narrative}</p>
          </Disclosure>
        )}
      </div>
    </div>
  );
}

function HypothesisDetail({ hyp, isTop }: { hyp: Hypothesis; isTop: boolean }) {
  const ev = useAsync(() => api.evidence(hyp.id), [hyp.id]);
  const paths: DepPath[] = ev.data?.symptom_paths ?? hyp.graph_paths;

  return (
    <Section
      className="hyp-detail"
      title={<>{hyp.service} <span className="muted">· {hyp.fault_class}</span></>}
      right={<div className="badges">{isTop ? <Badge tone="candidate">Root cause candidate</Badge> : <Badge>Alternative</Badge>}<Badge>Unverified</Badge></div>}
    >
      <p className="muted small">{hyp.fault_class_basis}</p>
      <div className="score-bars">
        <ScoreBar label="Local evidence" value={hyp.score.local_evidence} />
        <ScoreBar label="Graph coverage" value={hyp.score.coverage} />
        {hyp.score.memory > 0 && <ScoreBar label="Memory" value={hyp.score.memory} />}
      </div>

      {hyp.explained_services.length > 0 && (
        <div className="kv-line"><span className="muted">Explains symptoms in</span>
          <span className="chips inline">{hyp.explained_services.map((s) => <span key={s} className="chip">{s}</span>)}</span></div>
      )}

      {ev.error ? <ErrorNotice error={ev.error} /> : !ev.data ? <Loading label="Loading evidence" /> : (
        <>
          <h4>Supporting evidence <span className="muted">{ev.data.supporting.length}</span></h4>
          {ev.data.supporting.length === 0 ? <Empty>None recorded.</Empty> : (
            <table className="tbl compact">
              <thead><tr><th>Service</th><th>Signal</th><th>Type</th><th className="num" title="Robust z-score vs baseline">Score</th></tr></thead>
              <tbody>{ev.data.supporting.map((s) => (
                <tr key={s.observation} title={s.observation}><td>{s.service}</td><td>{s.signal}</td><td className="muted">{s.kind}</td><td className="num">{s.score.toFixed(1)}</td></tr>
              ))}</tbody>
            </table>
          )}
          <h4>Contradicting evidence <span className="muted">{ev.data.contradicting.length}</span></h4>
          {ev.data.contradicting.length === 0 ? <div className="muted small">None recorded.</div> : (
            <table className="tbl compact">
              <tbody>{ev.data.contradicting.map((s) => (
                <tr key={s.observation} title={s.observation}><td>{s.service}</td><td>{s.signal}</td><td className="num">{s.score?.toFixed(1)}</td></tr>
              ))}</tbody>
            </table>
          )}
        </>
      )}

      <h4>Evidence paths <span className="muted">{paths.length}</span></h4>
      {paths.length === 0 ? <div className="muted small">No dependency path from other anomalous services.</div> : (
        <ul className="paths">
          {paths.map((p) => (
            <li key={p.path.join(">")}>
              {p.path.map((s, i) => (
                <span key={i} className="path-step">
                  {i > 0 && <ArrowRight size={12} className="muted" aria-label={p.rel_types[i - 1]} />}
                  <span className={s === hyp.service ? "path-node root" : "path-node"}>{s}</span>
                </span>
              ))}
              <span className="path-src muted" title="Relationship provenance">{[...new Set(p.rel_sources)].map((x) => (x === "trace" ? "trace" : "architecture")).join(", ")}</span>
            </li>
          ))}
        </ul>
      )}

      {ev.data && ev.data.memories.length > 0 && (
        <>
          <h4>Informed by memory</h4>
          <ul className="chips">{ev.data.memories.map((m) => <li key={m.memory}><span className="chip" title={m.effect}>{m.memory} · {m.effect}</span></li>)}</ul>
        </>
      )}

      {hyp.rationale.length > 0 && (
        <Disclosure title="Ranking rationale">
          <ul className="plain">{hyp.rationale.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </Disclosure>
      )}
    </Section>
  );
}
