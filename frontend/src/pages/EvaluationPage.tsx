import { useMemo, useState } from "react";
import { api, EvalRow, Evaluation, Summary } from "../api";
import { Badge, Disclosure, Empty, ErrorNotice, Loading, OUTCOME_TONE, Section, Segmented } from "../components/ui";
import { humanize, modeLabel, ms, pct, when } from "../lib/format";
import { useAsync } from "../lib/useAsync";

type Split = "test" | "validation" | "history" | "synthetic";
const SPLITS: { id: Split; label: string; key: keyof Evaluation; note: string; rows?: keyof Evaluation }[] = [
  { id: "test", label: "Test", key: "test_summary", rows: "rows_test", note: "Held-out RCAEval repetition 3, untouched during development." },
  { id: "validation", label: "Validation", key: "validation_summary", rows: "rows_validation", note: "RCAEval repetition 2, used for failure analysis; optimistic." },
  { id: "history", label: "Development", key: "history_summary_development_set", note: "RCAEval repetition 1, used to develop ranking weights; optimistic." },
  { id: "synthetic", label: "Scenarios", key: "synthetic_summary", rows: "rows_synthetic", note: "Hand-designed scenarios with deployments and prior repairs." },
];

type Fmt = "pct" | "count" | "ms";
const GROUPS: { title: string; metrics: { key: string; label: string; fmt: Fmt; tip: string; lowerBetter?: boolean }[] }[] = [
  { title: "Root-cause localization", metrics: [
    { key: "top1", label: "Top-1 accuracy", fmt: "pct", tip: "True root-cause service ranked first" },
    { key: "top3", label: "Top-3 accuracy", fmt: "pct", tip: "True root-cause service within the first three hypotheses" },
    { key: "avg5", label: "Avg@5", fmt: "pct", tip: "Mean of Top-1 … Top-5 accuracy (RCAEval metric)" },
    { key: "fault_class_acc", label: "Fault class accuracy", fmt: "pct", tip: "Inferred fault class matches the injected fault" },
    { key: "abstained", label: "Abstained", fmt: "count", tip: "Investigations concluded inconclusive", lowerBetter: true },
  ] },
  { title: "Blast radius", metrics: [
    { key: "blast_precision", label: "Precision", fmt: "pct", tip: "Predicted affected services that were actually anomalous" },
    { key: "blast_recall", label: "Recall", fmt: "pct", tip: "Anomalous services covered by the predicted blast radius" },
  ] },
  { title: "Remediation (simulated)", metrics: [
    { key: "mitigation_success_rate", label: "Remediation rate", fmt: "pct", tip: "Top recommended action resolved the incident in the simulator" },
    { key: "inappropriate_action_rate", label: "Ineffective actions", fmt: "pct", tip: "1 − remediation rate, among cases where an action was recommended", lowerBetter: true },
    { key: "worsened", label: "Worsened", fmt: "count", tip: "Actions that caused a side effect on a healthy request-path service", lowerBetter: true },
    { key: "evidence_validity", label: "Evidence validity", fmt: "pct", tip: "Cited evidence IDs that exist in the graph for the incident" },
  ] },
  { title: "Latency", metrics: [
    { key: "latency_ms_median", label: "Latency (p50)", fmt: "ms", tip: "Median end-to-end investigation time", lowerBetter: true },
    { key: "latency_ms_p95", label: "Latency (p95)", fmt: "ms", tip: "95th percentile investigation time", lowerBetter: true },
  ] },
];

const fmt = (v: number | null | undefined, f: Fmt) => (v == null ? "—" : f === "pct" ? pct(v) : f === "ms" ? ms(v) : String(v));
const colLabel = (m: string) => (m === "C_loso_control" ? "Other-service memory (control)" : modeLabel(m));

export default function EvaluationPage() {
  const ev = useAsync(() => api.evaluation(), []);
  const [split, setSplit] = useState<Split>("test");

  if (ev.error) return <div className="page-pad"><ErrorNotice error={ev.error} /></div>;
  if (!ev.data) return <Loading label="Loading evaluation" />;
  const e = ev.data;
  const def = SPLITS.find((s) => s.id === split)!;
  const summary = e[def.key] as Summary;
  const rows = def.rows ? (e[def.rows] as EvalRow[] | undefined) ?? [] : [];

  return (
    <div className="page-pad evaluation">
      <Overview s={e.test_summary} n={e.test_summary.C_graph_memory?.n ?? null} />

      <Section title="Results by mode" right={<Segmented label="Split" options={SPLITS} value={split} onChange={setSplit} />}>
        <p className="muted small">{def.note}</p>
        <MetricTable s={summary} />
      </Section>

      {rows.length > 0 && <CaseTable rows={rows} />}

      <Disclosure title="Run details">
        <dl className="kv">
          <dt>Generated</dt><dd>{when(e.generated_at)}{e.elapsed_s != null && ` · ${e.elapsed_s.toFixed(0)} s`}</dd>
          {e.dataset.source && (<><dt>Dataset</dt><dd>{e.dataset.source.dataset} · {e.dataset.source.hf_repo} @ <span className="mono">{e.dataset.source.revision?.slice(0, 10)}</span> · {e.dataset.source.license}</dd></>)}
          <dt>Cases</dt><dd>{["rcaeval_history", "rcaeval_validation", "rcaeval_test", "synthetic"].filter((k) => e.dataset[k] != null).map((k) => `${humanize(k.replace("rcaeval_", ""))} ${e.dataset[k]}`).join(" · ")}</dd>
          <dt>Leakage check</dt><dd>{e.leakage_issues.length === 0 ? "No issues" : `${e.leakage_issues.length} issues`}</dd>
          <dt>Graph integrity</dt><dd>{e.integrity_ok ? "OK" : "Problems found"}</dd>
        </dl>
      </Disclosure>
    </div>
  );
}

function Overview({ s, n }: { s: Summary; n: number | null }) {
  const c = s.C_graph_memory, a = s.A_incident_only;
  if (!c) return null;
  const cards: { label: string; key: string; fmt: Fmt; tip: string; lowerBetter?: boolean }[] = [
    { label: "Top-1 accuracy", key: "top1", fmt: "pct", tip: "True root cause ranked first" },
    { label: "Avg@5", key: "avg5", fmt: "pct", tip: "Mean of Top-1 … Top-5 accuracy" },
    { label: "Remediation rate", key: "mitigation_success_rate", fmt: "pct", tip: "Top action resolved the incident in the simulator" },
    { label: "Blast-radius precision", key: "blast_precision", fmt: "pct", tip: "Predicted affected services that were anomalous" },
    { label: "Blast-radius recall", key: "blast_recall", fmt: "pct", tip: "Anomalous services covered by the prediction" },
    { label: "Latency (p50)", key: "latency_ms_median", fmt: "ms", tip: "Median investigation time", lowerBetter: true },
  ];
  return (
    <Section title="Test split · Graph + Memory" right={<span className="muted small">{n} held-out benchmark cases · compared with the incident-only baseline</span>}>
      <div className="metric-cards">
        {cards.map((k) => {
          const v = c[k.key], b = a?.[k.key];
          const d = v != null && b != null ? v - b : null;
          const better = d == null || d === 0 ? null : (d > 0) !== !!k.lowerBetter;
          return (
            <div key={k.key} className="metric-card" title={k.tip}>
              <span className="metric-label">{k.label}</span>
              <span className="metric-val">{fmt(v, k.fmt)}</span>
              {d != null && (
                <span className={`metric-delta ${better == null ? "muted" : better ? "tone-good" : "tone-bad"}`}>
                  {d === 0 ? "same as baseline" : `${d > 0 ? "+" : "−"}${k.fmt === "pct" ? `${Math.abs(d * 100).toFixed(1)} pts` : ms(Math.abs(d))} vs baseline`}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function MetricTable({ s }: { s: Summary }) {
  const modes = Object.keys(s);
  if (!modes.length) return <Empty>No results for this split.</Empty>;
  return (
    <div className="table-scroll">
      <table className="tbl metric-table">
        <thead>
          <tr><th>Metric</th>{modes.map((m) => <th key={m} className="num" title={m}>{colLabel(m)}</th>)}</tr>
          <tr className="sub"><td className="muted">Samples</td>{modes.map((m) => <td key={m} className="num muted">{s[m].n}</td>)}</tr>
        </thead>
        {GROUPS.map((g) => (
          <tbody key={g.title}>
            <tr className="group"><th colSpan={modes.length + 1}>{g.title}</th></tr>
            {g.metrics.map((k) => {
              const vals = modes.map((m) => s[m][k.key]).filter((v): v is number => v != null);
              const best = vals.length > 1 ? (k.lowerBetter ? Math.min(...vals) : Math.max(...vals)) : null;
              return (
                <tr key={k.key}>
                  <td title={k.tip}><span className="has-tip">{k.label}</span></td>
                  {modes.map((m) => {
                    const v = s[m][k.key];
                    return <td key={m} className={`num${v != null && v === best && new Set(vals).size > 1 ? " best" : ""}`}>{fmt(v, k.fmt)}</td>;
                  })}
                </tr>
              );
            })}
          </tbody>
        ))}
      </table>
    </div>
  );
}

function CaseTable({ rows }: { rows: EvalRow[] }) {
  const modes = useMemo(() => [...new Set(rows.map((r) => r.mode))], [rows]);
  const [mode, setMode] = useState(modes.includes("C_graph_memory") ? "C_graph_memory" : modes[0]);
  const [missesOnly, setMissesOnly] = useState(false);
  const shown = rows.filter((r) => r.mode === mode && (!missesOnly || !r.top1));
  return (
    <Disclosure title="Per-case results" meta="includes ground truth">
      <div className="filters">
        <select value={mode} onChange={(e) => setMode(e.target.value)} aria-label="Mode">{modes.map((m) => <option key={m} value={m}>{colLabel(m)}</option>)}</select>
        <label className="check"><input type="checkbox" checked={missesOnly} onChange={(e) => setMissesOnly(e.target.checked)} /> Top-1 misses only</label>
        <span className="muted small">{shown.length} cases</span>
      </div>
      <div className="table-scroll">
        <table className="tbl compact">
          <thead><tr><th>Incident</th><th>True root · fault</th><th>Predicted</th><th>Fault class</th><th>Top action</th><th>Outcome</th></tr></thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.incident_id} className={r.top1 ? "" : "miss"}>
                <td className="mono">{r.incident_id}</td>
                <td>{r.truth_root} <span className="muted">· {r.truth_fault}</span></td>
                <td>{r.predicted ?? <span className="muted">inconclusive</span>}</td>
                <td className={r.fault_class_ok === false ? "tone-warn" : ""}>{r.fault_class_pred ?? "—"}</td>
                <td>{r.action ? `${humanize(r.action.type)} · ${r.action.target}` : "—"}</td>
                <td>{r.action_outcome ? <Badge tone={OUTCOME_TONE[r.action_outcome] ?? "neutral"}>{humanize(r.action_outcome)}</Badge> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Disclosure>
  );
}
