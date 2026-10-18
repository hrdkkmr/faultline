import { useEffect, useState } from "react";
import { api, MemoryRow, TimelineRow } from "../api";
import { Empty, ErrorBox, Panel, Tag } from "./common";

export default function MemoryPage({ refreshKey }: { refreshKey: number }) {
  const [mem, setMem] = useState<MemoryRow[] | null>(null);
  const [tl, setTl] = useState<TimelineRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.memories(), api.timeline()]).then(([m, t]) => { setMem(m); setTl(t); })
      .catch((e) => setError((e as Error).message));
  }, [refreshKey]);

  if (error) return <ErrorBox error={error} />;
  if (!mem) return <div className="loading">Loading memory from FalkorDB…</div>;
  return (
    <div className="grid2">
      <Panel title={`Persistent memory (${mem.length})`} right={<Tag p="memory" />}>
        {mem.length === 0 ? <Empty>No memories yet. Simulate an action on an incident to create one.</Empty> : mem.map((m) => (
          <div key={m.id} className="mem">
            <div><code>{m.id}</code> <b>{m.action_type}</b> on {m.service} → <b className={m.outcome}>{m.outcome}</b> <Tag p="simulated" /></div>
            <div className="small">{m.lesson}</div>
            <div className="small">from <code>{m.derived_from}</code> · {m.created_at}</div>
            <div className="chips">{m.conditions.map((c) => <span key={c} className="chip">{c}</span>)}</div>
            {m.contradicts.length > 0 && <div className="small reason">⚠ conflicts with {m.contradicts.join(", ")} (both kept)</div>}
          </div>
        ))}
      </Panel>
      <Panel title="Incident timeline">
        {tl.length === 0 ? <Empty>No investigated incidents yet.</Empty> : (
          <ol className="timeline">
            {tl.map((t) => (
              <li key={t.incident_id}>
                <div><b>{t.title}</b> <code>{t.incident_id}</code> · {t.status} · {t.investigations} investigation(s)</div>
                {t.actions.map((a, i) => (
                  <div key={i} className={`small outcome ${a.outcome}`}>
                    <Tag p="simulated" /> {a.action} on {a.target} → {a.outcome} {a.memory && <>· <Tag p="memory">{a.memory}</Tag></>}
                    {a.side_effects?.map((s) => <div key={s}>⚠ {s}</div>)}
                  </div>
                ))}
              </li>
            ))}
          </ol>
        )}
      </Panel>
    </div>
  );
}
