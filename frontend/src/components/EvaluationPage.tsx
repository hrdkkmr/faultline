import { useEffect, useState } from "react";
import { api, Evaluation, Summary } from "../api";
import { ErrorBox, Panel, pct, Tag } from "./common";

const COLS: [string, string, boolean][] = [
  ["top1", "Top-1", true], ["top3", "Top-3", true], ["avg5", "Avg@5", true], ["fault_class_acc", "Fault class", true],
  ["mitigation_success_rate", "Mitigation success", true], ["inappropriate_action_rate", "Inappropriate action", true],
  ["worsened", "Worsened", false], ["evidence_validity", "Evidence valid", true], ["blast_precision", "Blast P", true],
  ["blast_recall", "Blast R", true], ["latency_ms_median", "Median ms", false],
];

function SummaryTable({ s }: { s: Summary }) {
  return (
    <table className="tbl">
      <thead><tr><th>mode</th><th>n</th>{COLS.map(([, l]) => <th key={l}>{l}</th>)}</tr></thead>
      <tbody>
        {Object.entries(s).map(([m, v]) => (
          <tr key={m}><td><b>{m}</b></td><td>{v.n}</td>
            {COLS.map(([k, , isPct]) => <td key={k}>{v[k] == null ? "—" : isPct ? pct(v[k]) : v[k]}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}

export default function EvaluationPage() {
  const [ev, setEv] = useState<Evaluation | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.evaluation().then(setEv).catch((e) => setError((e as Error).message)); }, []);
  if (error) return <ErrorBox error={error} />;
  if (!ev) return <div className="loading">Loading evaluation results…</div>;
  return (
    <div className="evaluation">
      <p className="small">
        Generated {ev.generated_at} by <code>python scripts/evaluate.py</code> on a separate graph. Leakage issues: {ev.leakage_issues.length} ·
        integrity ok: {String(ev.integrity_ok)}. Mitigation outcomes are <Tag p="simulated" />. Ground truth is shown only on this page <Tag p="truth" />.
      </p>
      <Panel title="TEST split — RCAEval RE2-OB repetition 3 (untouched during development)"><SummaryTable s={ev.test_summary} /></Panel>
      <Panel title="VALIDATION split — repetition 2 (used for failure analysis; optimistic)"><SummaryTable s={ev.validation_summary} /></Panel>
      <Panel title="History — repetition 1 (development set)"><SummaryTable s={ev.history_summary_development_set} /></Panel>
      <Panel title="Synthetic scenarios (hand-designed)"><SummaryTable s={ev.synthetic_summary} /></Panel>
      <Panel title="Per-case results, TEST split, mode C" right={<Tag p="truth" />}>
        <table className="tbl">
          <thead><tr><th>incident</th><th>truth root / fault</th><th>predicted</th><th>fault class</th><th>action</th><th>outcome</th></tr></thead>
          <tbody>
            {ev.rows_test.filter((r) => r.mode === "C_graph_memory").map((r) => (
              <tr key={r.incident_id} className={r.top1 ? "" : "miss"}>
                <td><code>{r.incident_id}</code></td><td>{r.truth_root} / {r.truth_fault}</td><td>{r.predicted ?? "inconclusive"}</td>
                <td>{r.fault_class_pred}</td><td>{r.action ? `${r.action.type} ${r.action.target}` : "—"}</td><td>{r.action_outcome ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
