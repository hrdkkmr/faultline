import type { Mode } from "../api";

export const MODES: { id: Mode; label: string; short: string }[] = [
  { id: "C_graph_memory", label: "Graph + Memory", short: "Graph + Memory" },
  { id: "B_graph", label: "Graph only", short: "Graph" },
  { id: "A_incident_only", label: "Incident only (baseline)", short: "Baseline" },
];

export const modeLabel = (m: string) => MODES.find((x) => x.id === m)?.label ?? (m === "C_loso_control" ? "Graph + Memory (other-service memory only)" : m);

export const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? "—" : `${(v * 100).toFixed(digits).replace(/\.0+$/, "")}%`;

export const num = (v: number | null | undefined, digits = 2) => (v == null ? "—" : v.toFixed(digits));

export const ms = (v: number | null | undefined) => (v == null ? "—" : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`);

/** "2026-09-01T10:40:00+00:00" -> "2026-09-01 10:40 UTC" */
export const when = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().slice(0, 16).replace("T", " ")} UTC`;
};

export const whenEpoch = (s: number | null | undefined) => (s == null ? "—" : when(new Date(s * 1000).toISOString()));

/** Strips redundant "[synthetic]" prefixes (source is shown as its own badge). */
export const cleanTitle = (t: string | null | undefined) => (t ?? "").replace(/^\[synthetic\]\s*/i, "");

export const humanize = (s: string | null | undefined) => (s ?? "").replace(/_/g, " ");

export const actionLabel = (type: string) => {
  const h = humanize(type);
  return h.charAt(0).toUpperCase() + h.slice(1);
};

export const SOURCE_LABEL: Record<string, string> = { synthetic: "Scenario", rcaeval: "Benchmark" };
export const sourceLabel = (s: string | null | undefined) => SOURCE_LABEL[s ?? ""] ?? (s || "unknown");

export const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  investigated: "Investigated",
  resolved: "Resolved",
  mitigation_failed: "Mitigation failed",
};
export const statusLabel = (s: string | null | undefined) => STATUS_LABEL[s ?? ""] ?? humanize(s);

/** "redis|mem|up" -> "redis mem ↑" */
export const signalLabel = (key: string) => {
  const [svc, sig, dir] = key.split("|");
  return `${svc} ${sig}${dir === "up" ? " ↑" : dir === "down" ? " ↓" : ""}`;
};

export const shortService = (s: string) => (s === "frontend-external" ? "frontend-ext" : s.replace(/service$/, ""));

export const fmtValue = (v: number | null | undefined) =>
  v == null ? "—" : Math.abs(v) >= 10000 || (Math.abs(v) > 0 && Math.abs(v) < 0.001) ? v.toExponential(2) : String(+v.toFixed(3));
