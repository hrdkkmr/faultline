import { FlaskConical, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { api, Mitigation, SimResult } from "../../api";
import { Badge, Disclosure, Empty, ErrorNotice, Meta, OUTCOME_TONE, RISK_TONE, Spinner, VERDICT_TONE } from "../../components/ui";
import { actionLabel, humanize, when } from "../../lib/format";
import { useAsync } from "../../lib/useAsync";
import type { WorkspaceData } from "../IncidentWorkspace";

const key = (m: Mitigation) => `${m.action.type}:${m.action.target}`;

export default function MitigationsTab({ data, onSimulated }: { data: WorkspaceData; onSimulated: () => void }) {
  const { inc, report } = data;
  const [tick, setTick] = useState(0);
  // Outcomes already recorded for this incident (persisted in the graph), so status survives reloads.
  const timeline = useAsync(() => api.timeline(), [tick]);
  const recorded = new Map<string, { outcome: string; at: string }>();
  timeline.data?.find((t) => t.incident_id === inc.id)?.actions.forEach((a) => recorded.set(`${a.action}:${a.target}`, { outcome: a.outcome, at: a.at }));

  if (!report) return <div className="tab-empty"><p>Run an investigation to get candidate mitigations.</p></div>;
  const ms = report.candidate_mitigations;
  const main = ms.filter((m) => m.verdict !== "not_recommended");
  const rejected = ms.filter((m) => m.verdict === "not_recommended");
  const done = () => { setTick((t) => t + 1); onSimulated(); };

  return (
    <div className="mitigations">
      <div className="notice notice-sim">
        <FlaskConical size={15} aria-hidden />
        <span><b>Simulation only.</b> Actions run against the repair simulator; nothing is executed on real infrastructure.</span>
      </div>
      {timeline.error != null && <ErrorNotice error={timeline.error} />}
      {ms.length === 0 ? <Empty>No candidate mitigations.</Empty> : (
        <>
          <div className="mit-list" role="list">
            {main.map((m) => <MitigationRow key={key(m)} m={m} incidentId={inc.id} recorded={recorded.get(key(m))} onDone={done} />)}
            {main.length === 0 && <Empty>No action is recommended for this run.</Empty>}
          </div>
          {rejected.length > 0 && (
            <Disclosure title="Not recommended" meta={rejected.length}>
              <div className="mit-list" role="list">
                {rejected.map((m) => <MitigationRow key={key(m)} m={m} incidentId={inc.id} recorded={recorded.get(key(m))} onDone={done} />)}
              </div>
            </Disclosure>
          )}
        </>
      )}
    </div>
  );
}

function MitigationRow({ m, incidentId, recorded, onDone }: {
  m: Mitigation; incidentId: string; recorded?: { outcome: string; at: string }; onDone: () => void;
}) {
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SimResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const simulatable = m.action.type !== "gather_more_evidence";
  const blocked = m.requires_approval && !approved;

  async function simulate() {
    setBusy(true); setError(null);
    try {
      setResult(await api.simulate(incidentId, m.action.type, m.action.target, approved));
      onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const outcome = result?.outcome.result ?? recorded?.outcome;
  return (
    <div className={`mit-row v-${m.verdict}`} role="listitem">
      <div className="mit-main">
        <div className="mit-name">
          <b>{actionLabel(m.action.type)}</b>{m.action.target && <span className="muted"> on </span>}{m.action.target && <b>{m.action.target}</b>}
        </div>
        <div className="mit-badges">
          <Meta tone={VERDICT_TONE[m.verdict] ?? "neutral"}>{humanize(m.verdict)}</Meta>
          {m.risk && <Meta tone={RISK_TONE[m.risk] ?? "neutral"} title="Risk level from the action catalog">{m.risk} risk</Meta>}
          {m.requires_approval && <Meta title="Disruptive action: needs explicit approval before simulation">needs approval</Meta>}
          {m.memory_effect !== 0 && (
            <Meta tone={m.memory_effect > 0 ? "good" : "bad"} title="Net effect of matching past outcomes in memory (best success minus best failure)">
              memory {m.memory_effect > 0 ? "+" : ""}{m.memory_effect.toFixed(2)}
            </Meta>
          )}
          {m.blockers.length > 0 && <Meta tone="bad">{m.blockers.length} blocker{m.blockers.length > 1 ? "s" : ""}</Meta>}
        </div>
        <div className="mit-status">
          {outcome ? (
            <span title={result ? result.outcome.detail : recorded ? `Recorded ${when(recorded.at)}` : undefined}>
              <span className="muted">Simulated · </span><Badge tone={OUTCOME_TONE[outcome] ?? "neutral"}>{humanize(outcome)}</Badge>
            </span>
          ) : <span className="muted">Proposed</span>}
        </div>
        <div className="mit-actions">
          {simulatable ? (
            <>
              {m.requires_approval && (
                <label className="check" title="Approve this disruptive action for simulation">
                  <input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} /> Approve
                </label>
              )}
              <button onClick={simulate} disabled={busy || blocked} title={blocked ? "Approve first" : "Run in the repair simulator"}>
                {busy ? <Spinner size={13} /> : <FlaskConical size={13} />} Simulate
              </button>
            </>
          ) : <span className="muted small">Collect more telemetry</span>}
        </div>
      </div>

      {error != null && <ErrorNotice error={error} />}
      {result && (
        <div className={`sim-result tone-bg-${OUTCOME_TONE[result.outcome.result] ?? "neutral"}`}>
          <span>{result.outcome.detail}</span>
          {result.outcome.side_effects.map((s) => <span key={s} className="side-effect"><TriangleAlert size={12} /> {s}</span>)}
          <span className="muted small">{result.duplicate ? "Already recorded as" : "Recorded as"} memory <span className="mono">{result.memory_id}</span></span>
        </div>
      )}

      {(m.preconditions_met.length > 0 || m.blockers.length > 0 || m.evidence.length > 0) && (
        <Disclosure title="Preconditions and evidence">
          {m.blockers.length > 0 && (<><h4>Blockers</h4><ul className="plain bad">{m.blockers.map((b) => <li key={b}>{b}</li>)}</ul></>)}
          {m.preconditions_met.length > 0 && (<><h4>Preconditions met</h4><ul className="plain">{m.preconditions_met.map((p) => <li key={p}>{p}</li>)}</ul></>)}
          {m.evidence.length > 0 && (<><h4>Evidence</h4><ul className="plain mono small">{m.evidence.map((e) => <li key={e}>{e}</li>)}</ul></>)}
        </Disclosure>
      )}
    </div>
  );
}
