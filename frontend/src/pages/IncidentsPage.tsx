import { PanelLeft, RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, IncidentRow } from "../api";
import { Empty, ErrorNotice, IconButton, Loading, StatusText } from "../components/ui";
import { cleanTitle, shortService, sourceLabel, statusLabel } from "../lib/format";
import GuideHint from "../components/GuideHint";
import { href, Route } from "../lib/router";
import { useAsync } from "../lib/useAsync";
import IncidentWorkspace from "./IncidentWorkspace";

type SourceFilter = "all" | "synthetic" | "rcaeval";

export default function IncidentsPage({ route }: { route: Route }) {
  const list = useAsync(() => api.incidents(), []);
  const [q, setQ] = useState("");
  const [source, setSource] = useState<SourceFilter>("all");
  const [status, setStatus] = useState("all");
  const [listOpen, setListOpen] = useState(() => !(route.incident && window.innerWidth <= 760));
  // On phone widths the list and workspace share the screen; picking an incident shows the workspace.
  useEffect(() => { if (route.incident && window.innerWidth <= 760) setListOpen(false); }, [route.incident]);

  // Select the first incident when none is in the URL (replace, so Back still works).
  useEffect(() => {
    if (!route.incident && list.data?.length) {
      window.location.replace(href({ page: "incidents", incident: list.data[0].id }));
    }
  }, [route.incident, list.data]);

  const statuses = useMemo(() => [...new Set((list.data ?? []).map((i) => i.status))].sort(), [list.data]);
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (list.data ?? []).filter((i) =>
      (source === "all" || i.source === source) &&
      (status === "all" || i.status === status) &&
      (!needle || i.id.toLowerCase().includes(needle) || i.title.toLowerCase().includes(needle) ||
        i.anomalous_services.some((s) => s.includes(needle))));
  }, [list.data, q, source, status]);

  return (
    <div className={`incidents-layout ${listOpen ? "" : "list-collapsed"}`}>
      <aside className="incident-list" aria-label="Incidents">
        <div className="list-head">
          <div className="list-head-title">
            <h2>Incidents</h2>
            {list.data && <span className="list-count">{shown.length} of {list.data.length}</span>}
          </div>
          <div className="search">
            <Search size={14} aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search ID, title, service" aria-label="Search incidents" />
          </div>
          <div className="list-filters">
            <select value={source} onChange={(e) => setSource(e.target.value as SourceFilter)} aria-label="Source">
              <option value="all">All sources</option>
              <option value="synthetic">Scenarios</option>
              <option value="rcaeval">Benchmark</option>
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
              <option value="all">Any status</option>
              {statuses.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
            </select>
            <IconButton label="Reload incidents" onClick={list.reload}><RefreshCw size={14} /></IconButton>
          </div>
        </div>
        <div className="list-body">
          {list.error ? <ErrorNotice error={list.error} /> : !list.data ? <Loading label="Loading incidents" /> :
            list.data.length === 0 ? <Empty>No incidents in the graph. Run the ingestion script with <code>--load-graph</code>.</Empty> :
            shown.length === 0 ? <Empty>No incidents match the filters.</Empty> :
            shown.map((i) => <ListItem key={i.id} i={i} selected={i.id === route.incident} />)}
        </div>
      </aside>
      <main className="workspace">
        <button className="list-toggle" onClick={() => setListOpen((o) => !o)} aria-expanded={listOpen} title={listOpen ? "Hide incident list" : "Show incident list"}>
          <PanelLeft size={15} /> <span>{listOpen ? "Hide list" : "Incidents"}</span>
        </button>
        <GuideHint />
        {route.incident
          ? <IncidentWorkspace key={route.incident} id={route.incident} tab={route.tab} onChanged={list.reload} />
          : list.data?.length === 0 ? null : <Loading />}
      </main>
    </div>
  );
}

function ListItem({ i, selected }: { i: IncidentRow; selected: boolean }) {
  const svcs = i.anomalous_services;
  const ref = useRef<HTMLAnchorElement>(null);
  useEffect(() => { if (selected) ref.current?.scrollIntoView({ block: "nearest" }); }, [selected]);
  return (
    <a ref={ref} className={`list-item${selected ? " selected" : ""}`} href={href({ page: "incidents", incident: i.id })} aria-current={selected ? "true" : undefined}>
      <div className="li-row">
        <span className="li-title">{cleanTitle(i.title)}</span>
      </div>
      <div className="li-row li-meta">
        <StatusText status={i.status} />
        <span>{sourceLabel(i.source)}</span>
        <span className="li-date">{i.detected_at_iso?.slice(0, 10)}</span>
      </div>
      <div className="li-row li-meta">
        <span className="mono">{i.id}</span>
        {svcs.length > 0 && <span className="li-svcs" title={svcs.join(", ")}>
          {svcs.slice(0, 2).map(shortService).join(", ")}{svcs.length > 2 ? ` +${svcs.length - 2}` : ""}
        </span>}
      </div>
    </a>
  );
}
