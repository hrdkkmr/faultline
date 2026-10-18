import { FileSearch, History, Network, Play, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, IncidentGraph, IncidentView, InvestigationRow, Mode, Report } from "../api";
import { ErrorNotice, Loading, Spinner, StatusText, TabDef, Tabs } from "../components/ui";
import { cleanTitle, MODES, modeLabel, ms, pct, shortService, sourceLabel, when } from "../lib/format";
import { go, IncidentTab } from "../lib/router";
import ArchitectureTab from "./tabs/ArchitectureTab";
import EvidenceTab from "./tabs/EvidenceTab";
import HistoryTab from "./tabs/HistoryTab";
import MitigationsTab from "./tabs/MitigationsTab";

export interface WorkspaceData {
  inc: IncidentView;
  graph: IncidentGraph;
  report: Report | null;
}

export default function IncidentWorkspace({ id, tab, onChanged }: { id: string; tab: IncidentTab; onChanged: () => void }) {
  const [inc, setInc] = useState<IncidentView | null>(null);
  const [graph, setGraph] = useState<IncidentGraph | null>(null);
  const [runs, setRuns] = useState<InvestigationRow[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [runError, setRunError] = useState<unknown>(null);
  const [mode, setMode] = useState<Mode>("C_graph_memory");
  const [running, setRunning] = useState(false);
  const [loadingRun, setLoadingRun] = useState(false);
  const [activity, setActivity] = useState(0); // bumps after simulations so history views refetch

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const [i, g, h] = await Promise.all([api.incident(id), api.graph(id), api.investigations(id)]);
      setInc(i); setGraph(g); setRuns(h);
      if (h.length) {
        setReport(await api.investigation(h[0].id));
        setMode(h[0].mode);
      }
    } catch (e) {
      setLoadError(e);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function investigate() {
    if (running) return;
    setRunning(true);
    setRunError(null);
    try {
      const r = await api.investigate(id, mode);
      setReport(r);
      const [h, i] = await Promise.all([api.investigations(id), api.incident(id)]);
      setRuns(h); setInc(i);
      onChanged();
    } catch (e) {
      setRunError(e);
    } finally {
      setRunning(false);
    }
  }

  async function selectRun(runId: string) {
    setLoadingRun(true);
    setRunError(null);
    try { setReport(await api.investigation(runId)); } catch (e) { setRunError(e); } finally { setLoadingRun(false); }
  }

  async function afterSimulation() {
    setActivity((a) => a + 1);
    onChanged();
    try { setInc(await api.incident(id)); } catch { /* summary refresh only; the simulation result is already shown */ }
  }

  if (loadError) return <div className="ws"><ErrorNotice error={loadError} action={<button onClick={load}>Retry</button>} /></div>;
  if (!inc || !graph) return <Loading label="Loading incident" />;

  const setTab = (t: IncidentTab) => go({ page: "incidents", incident: id, tab: t });
  const tabs: TabDef<IncidentTab>[] = [
    { id: "graph", label: "Architecture & Blast Radius", icon: <Network size={14} /> },
    { id: "evidence", label: "Root Cause & Evidence", icon: <FileSearch size={14} />, count: report?.hypotheses.length ?? null },
    { id: "mitigations", label: "Mitigations", icon: <ShieldCheck size={14} />, count: report?.candidate_mitigations.length ?? null },
    { id: "history", label: "Historical Context", icon: <History size={14} /> },
  ];
  const data: WorkspaceData = { inc, graph, report };
  const anomalous = graph.nodes.filter((n) => n.anomalous).map((n) => n.name);
  const affected = report?.affected_services;
  const conclusive = report && report.conclusion !== "inconclusive";

  return (
    <div className="ws">
      <header className="ws-head">
        <h1 className="ws-title" title={inc.description ?? undefined}>{cleanTitle(inc.title)}</h1>
        <div className="ws-meta">
          <span className="mono">{inc.id}</span>
          <StatusText status={inc.status} />
          <span title={inc.provenance}>{sourceLabel(inc.source)}</span>
          <span>{when(inc.detected_at_iso)}</span>
          <span className="telemetry" title="Telemetry available for this incident (struck through = missing)">
            {Object.entries(inc.telemetry).map(([k, v]) => <span key={k} className={v ? "" : "absent"}>{k}</span>)}
          </span>
        </div>
      </header>

      <div className="tiles" aria-label="Incident summary">
        <div className="tile">
          <span className="tile-label">Anomalous services</span>
          <span className={`tile-value${anomalous.length ? " tone-bad" : ""}`}>{anomalous.length}</span>
          <span className="tile-sub" title={anomalous.join(", ")}>{anomalous.length ? anomalous.map(shortService).join(", ") : "none observed"}</span>
        </div>
        <div className="tile">
          <span className="tile-label">Blast radius</span>
          <span className="tile-value">{affected?.potential ? affected.potential.length : "—"}</span>
          <span className="tile-sub">{!report ? "computed by an investigation" : affected?.potential
            ? `${affected.observed?.length ?? 0} already anomalous · from ${affected.root}` : "not computed in baseline mode"}</span>
        </div>
        <div className={`tile${conclusive ? " tile-candidate" : ""}`}>
          <span className="tile-label">Root cause candidate {conclusive && <span className="tag-unverified" title="A ranked hypothesis, not a confirmed cause">unverified</span>}</span>
          <span className="tile-value tile-value-text" title={conclusive ? report?.suspected_root_cause ?? undefined : undefined}>{!report ? "—" : conclusive ? report.suspected_root_cause : "Inconclusive"}</span>
          <span className="tile-sub">{!report ? "no investigation yet" : conclusive
            ? <>{report.suspected_fault_class} · <span title="Share of the total ranking score held by the top hypothesis. Not a probability.">score share {pct(report.confidence, 0)}</span></>
            : "evidence too weak to rank a cause"}</span>
        </div>
        <div className="tile tile-metal" aria-label="Investigation">
          <div className="metal-top">
            <span className="tile-label">Investigation</span>
            <span className="metal-status" role="status">
              {running ? <><Spinner size={12} /> Running</> : report ? `${modeLabel(report.mode)} · ${ms(report.elapsed_ms)}` : "Not investigated"}
              {loadingRun && <Spinner size={12} />}
            </span>
          </div>
          {runs.length > 0 && (
            <select className="metal-select" value={report?.investigation_id ?? ""} onChange={(e) => selectRun(e.target.value)} disabled={loadingRun || running} aria-label="Investigation run">
              {runs.map((r, n) => (
                <option key={r.id} value={r.id}>{n === 0 ? "Latest run · " : "Run · "}{modeLabel(r.mode)} · {r.created_at.slice(5, 16).replace("T", " ")}</option>
              ))}
            </select>
          )}
          <div className="metal-actions">
            <select className="metal-select" value={mode} onChange={(e) => setMode(e.target.value as Mode)} disabled={running} aria-label="Investigation mode">
              {MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
            <button className="btn-primary" onClick={investigate} disabled={running} aria-busy={running}>
              {running ? <Spinner /> : <Play size={14} />} {running ? "Investigating" : "Investigate"}
            </button>
          </div>
        </div>
      </div>

      {runError != null && <ErrorNotice error={runError} />}

      <Tabs tabs={tabs} value={tab} onChange={setTab} label="Investigation views" />

      <div className="ws-tabpanel" role="tabpanel">
        {tab === "graph" && <ArchitectureTab data={data} />}
        {tab === "evidence" && <EvidenceTab data={data} onInvestigate={investigate} running={running} />}
        {tab === "mitigations" && <MitigationsTab data={data} onSimulated={afterSimulation} />}
        {tab === "history" && <HistoryTab data={data} runs={runs} activity={activity} onSelectRun={selectRun} />}
      </div>
    </div>
  );
}
