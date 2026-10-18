import { useCallback, useEffect, useState } from "react";
import { api, IncidentRow } from "./api";
import { ErrorBox, Legend, Tag } from "./components/common";
import EvaluationPage from "./components/EvaluationPage";
import IncidentPage from "./components/IncidentPage";
import MemoryPage from "./components/MemoryPage";

type View = "incident" | "memory" | "evaluation";

export default function App() {
  const [view, setView] = useState<View>("incident");
  const [incidents, setIncidents] = useState<IncidentRow[] | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "synthetic" | "rcaeval">("all");
  const [health, setHealth] = useState<{ ok: boolean; text: string }>({ ok: false, text: "checking…" });
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);

  const loadIncidents = useCallback(async () => {
    try {
      const rows = await api.incidents();
      setIncidents(rows);
      setError(null);
      setSel((s) => s ?? rows[0]?.id ?? null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    api.health()
      .then(({ status, body }) => setHealth({ ok: status === 200, text: status === 200
        ? `FalkorDB ok · ${body.database.nodes} nodes · ${body.database.latency_ms} ms`
        : `FalkorDB unavailable: ${body.database?.error ?? status}` }))
      .catch(() => setHealth({ ok: false, text: "backend unreachable" }));
    loadIncidents();
  }, [loadIncidents, refresh]);

  const shown = (incidents ?? []).filter((i) => filter === "all" || i.source === filter);

  return (
    <div className="app">
      <header className="top">
        <div className="brand">Faultline <span>graph-native incident investigation on FalkorDB</span></div>
        <nav>
          {(["incident", "memory", "evaluation"] as View[]).map((v) => (
            <button key={v} className={view === v ? "active" : ""} onClick={() => setView(v)}>
              {v === "incident" ? "Investigate" : v === "memory" ? "Memory & timeline" : "Evaluation"}
            </button>
          ))}
        </nav>
        <div className={`health ${health.ok ? "ok" : "bad"}`}>{health.text}</div>
      </header>
      <Legend />
      <ErrorBox error={error} />
      <div className="body">
        {view === "incident" && (
          <aside className="sidebar">
            <div className="filter">
              {(["all", "synthetic", "rcaeval"] as const).map((f) => (
                <button key={f} className={filter === f ? "active" : ""} onClick={() => setFilter(f)}>{f}</button>
              ))}
            </div>
            {incidents === null ? <div className="loading">Loading…</div> : shown.length === 0 ? (
              <div className="empty">No incidents in the graph. Run <code>python scripts/ingest.py --load-graph</code>.</div>
            ) : shown.map((i) => (
              <button key={i.id} className={`inc ${sel === i.id ? "sel" : ""}`} onClick={() => setSel(i.id)}>
                <div className="inc-title">{i.title}</div>
                <div className="inc-meta">
                  <code>{i.id}</code> {i.source === "synthetic" ? <Tag p="synthetic">syn</Tag> : <Tag p="observed">RCAEval</Tag>}
                </div>
                <div className="inc-meta">{i.anomalous} anomalies · {i.status}{i.investigations ? ` · ${i.investigations} inv.` : ""}</div>
              </button>
            ))}
          </aside>
        )}
        <main>
          {view === "incident" && (sel ? <IncidentPage key={sel} id={sel} onChanged={() => loadIncidents()} /> : <div className="empty">Select an incident.</div>)}
          {view === "memory" && <MemoryPage refreshKey={refresh} />}
          {view === "evaluation" && <EvaluationPage />}
        </main>
      </div>
      <footer><button onClick={() => setRefresh((r) => r + 1)}>Refresh</button></footer>
    </div>
  );
}
