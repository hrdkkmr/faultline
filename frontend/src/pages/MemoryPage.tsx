import { RefreshCw, Search, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { api, MemoryRow, TimelineRow } from "../api";
import { Badge, Disclosure, Empty, ErrorNotice, IconButton, Loading, OUTCOME_TONE, STATUS_TONE, Tabs } from "../components/ui";
import { actionLabel, cleanTitle, humanize, signalLabel, sourceLabel, statusLabel, when, whenEpoch } from "../lib/format";
import { href } from "../lib/router";
import { AsyncState, useAsync } from "../lib/useAsync";

type Sub = "memories" | "timeline";

export default function MemoryPage() {
  const [sub, setSub] = useState<Sub>("memories");
  const mem = useAsync(() => api.memories(), []);
  const tl = useAsync(() => api.timeline(), []);
  const reload = () => { mem.reload(); tl.reload(); };

  return (
    <div className="page-pad">
      <div className="page-head">
        <Tabs<Sub> label="Memory views" value={sub} onChange={setSub} tabs={[
          { id: "memories", label: "Remediation memory", count: mem.data?.length ?? null },
          { id: "timeline", label: "Timeline", count: tl.data?.length ?? null },
        ]} />
        <IconButton label="Reload" onClick={reload}><RefreshCw size={14} /></IconButton>
      </div>
      <div className="mem-page">{sub === "memories" ? <Memories state={mem} /> : <Timeline state={tl} />}</div>
    </div>
  );
}

function Memories({ state }: { state: AsyncState<MemoryRow[]> }) {
  const [q, setQ] = useState("");
  const [outcome, setOutcome] = useState("all");
  const rows = useMemo(() => {
    const n = q.trim().toLowerCase();
    return (state.data ?? []).filter((m) => (outcome === "all" || m.outcome === outcome) &&
      (!n || [m.service, m.action_type, m.derived_from, m.id].some((x) => x?.toLowerCase().includes(n))));
  }, [state.data, q, outcome]);

  if (state.error) return <ErrorNotice error={state.error} />;
  if (!state.data) return <Loading label="Loading memory" />;
  if (state.data.length === 0) return <Empty>No memories yet. Simulating a mitigation records its outcome here.</Empty>;

  return (
    <>
      <div className="filters">
        <div className="search"><Search size={14} aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Service, action, incident" aria-label="Search memories" /></div>
        <select value={outcome} onChange={(e) => setOutcome(e.target.value)} aria-label="Outcome">
          <option value="all">Any outcome</option>
          <option value="resolved">Resolved</option>
          <option value="not_resolved">Not resolved</option>
          <option value="worsened">Worsened</option>
        </select>
        <span className="muted small">Outcomes come from the repair simulator.</span>
      </div>
      {rows.length === 0 ? <Empty>No memories match.</Empty> : (
        <div className="table-scroll"><table className="tbl mem-table">
          <thead><tr><th>Action</th><th>Outcome</th><th>Applies when</th><th>Learned from</th><th>Recorded</th></tr></thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id}>
                <td><b>{actionLabel(m.action_type)}</b> <span className="muted">on</span> {m.service}
                  {m.contradicts.length > 0 && <div className="small tone-warn" title={m.contradicts.join(", ")}><TriangleAlert size={11} /> Conflicts with {m.contradicts.length} earlier memor{m.contradicts.length > 1 ? "ies" : "y"} (kept)</div>}
                </td>
                <td><Badge tone={OUTCOME_TONE[m.outcome] ?? "neutral"}>{humanize(m.outcome)}</Badge></td>
                <td><div className="chips inline">{m.conditions.map((c) => <span key={c} className="chip">{signalLabel(c)}</span>)}</div></td>
                <td><a className="mono" href={href({ page: "incidents", incident: m.derived_from })}>{m.derived_from}</a>
                  <div className="muted small">{sourceLabel(m.incident_source)}</div></td>
                <td className="muted nowrap" title={m.id}>{when(m.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </>
  );
}

function Timeline({ state }: { state: AsyncState<TimelineRow[]> }) {
  const [source, setSource] = useState("all");
  const [withActions, setWithActions] = useState(false);
  const rows = useMemo(() => (state.data ?? [])
    .filter((t) => (source === "all" || t.source === source) && (!withActions || t.actions.length > 0)), [state.data, source, withActions]);

  if (state.error) return <ErrorNotice error={state.error} />;
  if (!state.data) return <Loading label="Loading timeline" />;
  if (state.data.length === 0) return <Empty>No investigated incidents yet.</Empty>;

  return (
    <>
      <div className="filters">
        <select value={source} onChange={(e) => setSource(e.target.value)} aria-label="Source">
          <option value="all">All sources</option><option value="synthetic">Scenarios</option><option value="rcaeval">Benchmark</option>
        </select>
        <label className="check"><input type="checkbox" checked={withActions} onChange={(e) => setWithActions(e.target.checked)} /> With actions only</label>
      </div>
      {rows.length === 0 ? <Empty>No incidents match.</Empty> : (
        <ol className="timeline">
          {rows.map((t) => (
            <li key={t.incident_id} className={t.actions.length ? "has-actions" : ""}>
              <div className="tl-head">
                <span className="tl-date muted">{whenEpoch(t.detected_at)}</span>
                <a href={href({ page: "incidents", incident: t.incident_id })}><b>{cleanTitle(t.title)}</b></a>
                <Badge tone={STATUS_TONE[t.status] ?? "neutral"}>{statusLabel(t.status)}</Badge>
                <span className="muted small">{sourceLabel(t.source)} · {t.investigations} investigation{t.investigations === 1 ? "" : "s"}</span>
              </div>
              {t.actions.length > 0 && (
                <ul className="tl-actions">
                  {t.actions.map((a, i) => (
                    <li key={i}>
                      <span>{actionLabel(a.action)} on {a.target}</span>
                      <Badge tone={OUTCOME_TONE[a.outcome] ?? "neutral"}>{humanize(a.outcome)}</Badge>
                      <Badge tone="sim">simulated</Badge>
                      {a.memory && <span className="muted small">→ memory <span className="mono">{a.memory}</span></span>}
                      {a.side_effects && a.side_effects.length > 0 && (
                        <Disclosure title={`${a.side_effects.length} side effect${a.side_effects.length > 1 ? "s" : ""}`}>
                          {a.side_effects.map((s) => <div key={s} className="side-effect small"><TriangleAlert size={12} /> {s}</div>)}
                        </Disclosure>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}
    </>
  );
}
