import { TriangleAlert } from "lucide-react";
import { api, InvestigationRow, MemoryMatch } from "../../api";
import { Badge, Disclosure, Empty, ErrorNotice, Loading, OUTCOME_TONE, Section, VERDICT_TONE } from "../../components/ui";
import { actionLabel, cleanTitle, humanize, modeLabel, ms, pct, signalLabel, sourceLabel, when } from "../../lib/format";
import { href } from "../../lib/router";
import { useAsync } from "../../lib/useAsync";
import type { WorkspaceData } from "../IncidentWorkspace";

export default function HistoryTab({ data, runs, activity, onSelectRun }: {
  data: WorkspaceData; runs: InvestigationRow[]; activity: number; onSelectRun: (id: string) => void;
}) {
  const { inc, report } = data;
  const usedMemory = report?.mode === "C_graph_memory";
  // Report contents are what the selected run used; otherwise query the graph directly.
  const related = useAsync(() => (report ? Promise.resolve(report.related_incidents) : api.related(inc.id).then((r) => r.related)), [inc.id, report]);
  const memories = useAsync(() => (usedMemory ? Promise.resolve(report!.memories_considered) : api.incidentMemories(inc.id).then((r) => r.matches)),
    [inc.id, report, usedMemory, activity]);
  const timeline = useAsync(() => api.timeline(), [activity]);
  const actions = timeline.data?.find((t) => t.incident_id === inc.id)?.actions ?? [];

  return (
    <div className="history-grid">
      <Section title="Memories" right={<span className="muted small">{usedMemory ? "Used by this run" : report ? "Not used in this mode · current retrieval" : "Current retrieval"}</span>}>
        {memories.error ? <ErrorNotice error={memories.error} /> : !memories.data ? <Loading /> :
          memories.data.length === 0 ? <Empty>No stored memory matches this incident.</Empty> :
          <ul className="mem-list">{memories.data.map((m) => <MemoryItem key={m.memory_id} m={m} />)}</ul>}
      </Section>

      <Section title="Related incidents" right={<span className="muted small" title="Jaccard similarity over anomalous signal signatures">by shared signals</span>}>
        {related.error ? <ErrorNotice error={related.error} /> : !related.data ? <Loading /> :
          related.data.length === 0 ? <Empty>No incidents share anomalous signals.</Empty> : (
            <ul className="rows">
              {related.data.map((r) => (
                <li key={r.incident_id}>
                  <a className="row-btn" href={href({ page: "incidents", incident: r.incident_id })}>
                    <span className="row-main">{cleanTitle(r.title)}</span>
                    <span className="row-meta" title="Jaccard similarity">{pct(r.jaccard, 0)}</span>
                  </a>
                  <div className="row-sub muted">
                    <span className="mono">{r.incident_id}</span>{r.source && <> · {sourceLabel(r.source)}</>} · {r.shared.length} shared: {r.shared.slice(0, 3).map(signalLabel).join(", ")}{r.shared.length > 3 ? "…" : ""}
                  </div>
                </li>
              ))}
            </ul>
          )}
      </Section>

      <Section title="Actions on this incident">
        {timeline.error ? <ErrorNotice error={timeline.error} /> : !timeline.data ? <Loading /> :
          actions.length === 0 ? <Empty>No actions recorded.</Empty> : (
            <ol className="tl">
              {actions.map((a, i) => (
                <li key={i}>
                  <div><b>{actionLabel(a.action)}</b> on {a.target} <Badge tone={OUTCOME_TONE[a.outcome] ?? "neutral"}>{humanize(a.outcome)}</Badge> <Badge tone="sim">simulated</Badge></div>
                  <div className="muted small">{when(a.at)}{a.memory && <> · memory <span className="mono">{a.memory}</span></>}</div>
                  {a.side_effects?.map((s) => <div key={s} className="side-effect small"><TriangleAlert size={12} /> {s}</div>)}
                </li>
              ))}
            </ol>
          )}
      </Section>

      <Section title="Investigation runs">
        {runs.length === 0 ? <Empty>No stored investigations.</Empty> : (
          <table className="tbl compact">
            <thead><tr><th>When</th><th>Mode</th><th>Result</th><th /></tr></thead>
            <tbody>{runs.map((r) => (
              <tr key={r.id} className={r.id === report?.investigation_id ? "current" : ""}>
                <td>{when(r.created_at)}</td>
                <td>{modeLabel(r.mode)}</td>
                <td>{r.conclusion === "inconclusive" ? <span className="muted">inconclusive</span> : <>{r.top_service}{r.fault_class && <span className="muted"> · {r.fault_class}</span>}</>}</td>
                <td>{r.id === report?.investigation_id ? <span className="muted small">shown</span> : <button className="link" onClick={() => onSelectRun(r.id)}>Open</button>}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
        {report && report.tool_calls.length > 0 && (
          <Disclosure title="Graph tool calls" meta={`${report.tool_calls.length} · ${ms(report.elapsed_ms)}`}>
            <table className="tbl compact">
              <thead><tr><th>Tool</th><th className="num">Rows</th><th className="num">Time</th></tr></thead>
              <tbody>{report.tool_calls.map((t, i) => (
                <tr key={i}><td className="mono">{t.tool}</td><td className="num">{t.results}</td><td className="num">{ms(t.ms)}</td></tr>
              ))}</tbody>
            </table>
          </Disclosure>
        )}
      </Section>
    </div>
  );
}

function MemoryItem({ m }: { m: MemoryMatch }) {
  return (
    <li className={`mem-item m-${m.verdict}`}>
      <div className="mem-head">
        <Badge tone={VERDICT_TONE[m.verdict]}>{m.verdict}</Badge>
        <span><b>{actionLabel(m.action_type)}</b> on {m.service}</span>
        <Badge tone={OUTCOME_TONE[m.outcome] ?? "neutral"}>{humanize(m.outcome)}</Badge>
      </div>
      <div className="muted small">
        From <a href={href({ page: "incidents", incident: m.derived_from })} className="mono">{m.derived_from}</a>
        {" · "}conditions matched {m.matched_conditions.length}/{m.required_conditions.length}
        {" · "}<span title="Similarity of the source incident's signal signature">similarity {pct(m.source_similarity, 0)}</span>
      </div>
      {m.reasons.length > 0 && <ul className="plain small reasons">{m.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      {m.contradicted_by.length > 0 && <div className="small tone-warn">Contradicted by {m.contradicted_by.join(", ")} (both kept)</div>}
      {(m.missing_conditions.length > 0 || m.matched_conditions.length > 0) && (
        <Disclosure title="Conditions">
          <div className="chips inline">
            {m.matched_conditions.map((c) => <span key={c} className="chip chip-good" title="Present in this incident">{signalLabel(c)}</span>)}
            {m.missing_conditions.map((c) => <span key={c} className="chip chip-missing" title="Required but not observed here">{signalLabel(c)}</span>)}
          </div>
        </Disclosure>
      )}
    </li>
  );
}
