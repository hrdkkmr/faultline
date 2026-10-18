import { CircleHelp, FlaskConical, History, Network } from "lucide-react";
import { ReactNode, useEffect, useState } from "react";
import { api, Health } from "./api";
import { href, Page, useRoute } from "./lib/router";
import EvaluationPage from "./pages/EvaluationPage";
import GuidePage from "./pages/guide/GuidePage";
import IncidentsPage from "./pages/IncidentsPage";
import MemoryPage from "./pages/MemoryPage";

const NAV: { id: Page; label: string; icon: ReactNode }[] = [
  { id: "incidents", label: "Incidents", icon: <Network size={18} /> },
  { id: "memory", label: "Memory & Timeline", icon: <History size={18} /> },
  { id: "evaluation", label: "Evaluation", icon: <FlaskConical size={18} /> },
];

export default function App() {
  const route = useRoute();
  // Remember the last incident so returning to "Incidents" keeps the selection.
  const [lastIncident, setLastIncident] = useState<string | null>(route.incident);
  useEffect(() => { if (route.incident) setLastIncident(route.incident); }, [route.incident]);
  const navHref = (p: Page) => (p === "incidents" ? href({ page: "incidents", incident: lastIncident }) : href({ page: p }));

  return (
    <div className="app">
      <nav className="rail" aria-label="Main">
        <a className="rail-logo" href={navHref("incidents")} title="Faultline" aria-label="Faultline home">
          <LogoMark />
        </a>
        <div className="rail-items">
          {NAV.map((n) => (
            <a key={n.id} href={navHref(n.id)} className={`rail-item${route.page === n.id ? " active" : ""}`}
              aria-current={route.page === n.id ? "page" : undefined} aria-label={n.label} data-tip={n.label}>
              {n.icon}<span className="rail-label">{n.label}</span>
            </a>
          ))}
        </div>
        <a href={href({ page: "guide" })} className={`rail-item rail-bottom${route.page === "guide" ? " active" : ""}`}
          aria-current={route.page === "guide" ? "page" : undefined} aria-label="How to use Faultline" data-tip="How to use">
          <CircleHelp size={18} /><span className="rail-label">Help</span>
        </a>
      </nav>

      <div className="main">
        <header className="topbar">
          <div className="brand">
            <span className="brand-name">Faultline</span>
            <span className="brand-sub">Incident Investigation</span>
          </div>
          <div className="topbar-right">
            <HealthIndicator />
            {route.page !== "guide" && <a className="pill-link" href={href({ page: "guide" })}><CircleHelp size={14} /> How to use</a>}
          </div>
        </header>
        <div className="page">
          {route.page === "incidents" && <IncidentsPage route={route} />}
          {route.page === "memory" && <MemoryPage />}
          {route.page === "evaluation" && <EvaluationPage />}
          {route.page === "guide" && <GuidePage section={route.section} lastIncident={lastIncident} />}
        </div>
      </div>
    </div>
  );
}

/** Faultline mark: two offset strata split by a fault line. */
function LogoMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
      <path d="M3 8h8l2 3h8" />
      <path d="M3 16h6l2-3" />
      <path d="M15 16h6" />
    </svg>
  );
}

function HealthIndicator() {
  const [state, setState] = useState<{ http: number; body: Health | null; error?: string } | null>(null);

  useEffect(() => {
    let alive = true;
    const check = () => api.health()
      .then(({ status, body }) => alive && setState({ http: status, body }))
      .catch((e) => alive && setState({ http: 0, body: null, error: (e as Error).message }));
    check();
    const t = window.setInterval(check, 30000);
    return () => { alive = false; window.clearInterval(t); };
  }, []);

  if (!state) return <div className="health"><span className="dot" /> Checking…</div>;
  if (!state.body) {
    return <div className="health bad" title={state.error} role="status"><span className="dot dot-bad" /> API unreachable</div>;
  }
  const db = state.body.database;
  const ok = db.status === "ok";
  const tip = ok
    ? `FalkorDB graph "${db.graph}" · ${db.nodes?.toLocaleString()} nodes · probe ${db.latency_ms} ms\nAPI ${state.body.app.status} (v${state.body.app.version})`
    : `FalkorDB graph "${db.graph}" unavailable: ${db.error ?? "no detail"}\nAPI ${state.body.app.status}`;
  return (
    <div className={`health ${ok ? "" : "bad"}`} title={tip} role="status" aria-label={ok ? "FalkorDB connected" : "FalkorDB unavailable"}>
      <span className={`dot ${ok ? "dot-good" : "dot-bad"}`} />
      <span>FalkorDB</span>
      {ok ? <span className="muted">{db.latency_ms} ms</span> : <span>unavailable</span>}
    </div>
  );
}
