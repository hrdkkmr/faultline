// Typed client for the Faultline backend. Every call hits a FalkorDB-backed endpoint; nothing is mocked.

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, message: string, detail: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

const SUMMARY: Record<number, string> = {
  0: "Backend unreachable",
  403: "Approval required",
  404: "Not found",
  409: "Conflict",
  422: "Invalid request",
  503: "Graph database unavailable",
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  } catch (e) {
    throw new ApiError(0, SUMMARY[0], (e as Error).message);
  }
  const text = await r.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!r.ok) {
    const b = body as { detail?: unknown; error?: string } | null;
    const detail = typeof b?.detail === "string" ? b.detail : JSON.stringify(b?.detail ?? b);
    throw new ApiError(r.status, SUMMARY[r.status] ?? `Request failed (${r.status})`, detail);
  }
  return body as T;
}

const enc = encodeURIComponent;

export const api = {
  health: async (): Promise<{ status: number; body: Health }> => {
    const r = await fetch("/health");
    return { status: r.status, body: await r.json() };
  },
  incidents: () => req<IncidentRow[]>("/api/incidents"),
  incident: (id: string) => req<IncidentView>(`/api/incidents/${enc(id)}`),
  graph: (id: string) => req<IncidentGraph>(`/api/incidents/${enc(id)}/graph`),
  investigate: (id: string, mode: Mode) =>
    req<Report>(`/api/incidents/${enc(id)}/investigate`, {
      method: "POST",
      body: JSON.stringify({ mode, persist: true, narrate: true }),
    }),
  investigations: (id: string) => req<InvestigationRow[]>(`/api/incidents/${enc(id)}/investigations`),
  investigation: (invId: string) => req<Report>(`/api/investigations/${enc(invId)}`),
  evidence: (hid: string) => req<EvidencePaths>(`/api/hypotheses/${enc(hid)}/evidence`),
  observation: (oid: string) => req<ObservationRecord>(`/api/observations/${enc(oid)}`),
  blastRadius: (service: string, incidentId?: string) =>
    req<BlastRadius>(`/api/services/${enc(service)}/blast-radius${incidentId ? `?incident_id=${enc(incidentId)}` : ""}`),
  related: (id: string) => req<{ incident_id: string; related: RelatedIncident[]; basis: string }>(`/api/incidents/${enc(id)}/related`),
  incidentMemories: (id: string) => req<{ incident_id: string; matches: MemoryMatch[]; basis: string }>(`/api/incidents/${enc(id)}/memories`),
  simulate: (id: string, type: string, target: string, approved: boolean) =>
    req<SimResult>(`/api/incidents/${enc(id)}/actions/simulate`, {
      method: "POST",
      body: JSON.stringify({ type, target, approved }),
    }),
  memories: () => req<MemoryRow[]>("/api/memories"),
  timeline: () => req<TimelineRow[]>("/api/timeline"),
  evaluation: () => req<Evaluation>("/api/evaluation"),
};

export type Mode = "A_incident_only" | "B_graph" | "C_graph_memory";

export interface Health {
  app: { status: string; version: string };
  database: { status: string; latency_ms?: number; graph: string; nodes?: number; error?: string };
}
export interface IncidentRow {
  id: string; title: string; source: string; status: string; detected_at: number;
  detected_at_iso: string; anomalous: number; anomalous_services: string[]; investigations: number;
}
export interface Observation {
  id: string; kind: string; service: string; linked_service: string | null; signal: string; score: number;
  direction: string; anomalous: boolean; baseline: number | null; observed: number | null; onset_s: number | null;
  caller: string | null; samples: string[]; raw_ref: string | null; source: string | null;
}
export interface IncidentView {
  id: string; title: string; description: string | null; source: string; status: string; system: string | null;
  detected_at: number | null; detected_at_iso: string; telemetry: Record<string, boolean>; provenance: string;
  observations: Observation[]; anomalous_services: string[];
}
export interface GraphNode {
  name: string; kind: string; language: string; otel: string; depends_on: string[]; anomalous: boolean;
  max_score: number; observations: string[];
}
export interface GraphEdge {
  source: string; target: string; type: "DEPENDS_ON" | "CALLS"; provenance: string; evidence: string | null;
  observed_in: number | null;
}
export interface IncidentGraph { incident_id: string; nodes: GraphNode[]; edges: GraphEdge[] }
export interface DepPath { service: string; depth: number; path: string[]; rel_types: string[]; rel_sources: (string | null)[] }
export interface Hypothesis {
  id: string; rank: number; service: string; fault_class: string; fault_class_basis: string;
  score: { local_evidence: number; coverage: number; memory: number; total: number };
  supporting_evidence: string[]; contradicting_evidence: string[]; explained_services: string[];
  graph_paths: DepPath[]; memories: string[]; rationale: string[];
}
export interface Mitigation {
  action: { type: string; target: string }; addresses_hypothesis: string; verdict: string; risk: string;
  requires_approval: boolean; preconditions_met: string[]; blockers: string[]; evidence: string[]; memory_effect: number;
}
export interface MemoryMatch {
  memory_id: string; derived_from: string; service: string; action_type: string; outcome: string; lesson: string;
  required_conditions: string[]; matched_conditions: string[]; missing_conditions: string[]; coverage: number;
  source_similarity: number; verdict: "applicable" | "partial" | "rejected"; reasons: string[]; contradicted_by: string[];
}
export interface BlastEntry { service: string; kind: string | null; depth: number; observed_impact: boolean; evidence: string[] }
export interface BlastRadius {
  service: string; incident_id: string | null; entries: BlastEntry[]; potential: string[]; observed: string[]; basis: string;
}
export interface RelatedIncident { incident_id: string; title: string; source?: string; shared: string[]; jaccard: number }
export interface ChangeRecord {
  id: string; service: string; at: number; version: string | null; previous_version?: string | null;
  change_type?: string | null; description?: string | null; source?: string | null;
}
export interface Report {
  investigation_id: string; incident_id: string; mode: Mode; conclusion: string; suspected_root_cause: string | null;
  suspected_fault_class: string | null; confidence: number; hypotheses: Hypothesis[];
  affected_services: { root?: string; potential?: string[]; observed?: string[]; entries?: BlastEntry[]; basis: string };
  candidate_mitigations: Mitigation[]; related_incidents: RelatedIncident[];
  memories_considered: MemoryMatch[];
  recent_changes: { changes?: ChangeRecord[]; data_available?: boolean; note?: string | null };
  missing_information: string[]; human_approval_required: boolean;
  tool_calls: { tool: string; args?: Record<string, unknown>; ms: number; results: number }[];
  narrative: string | null; narrative_source: string; created_at: string; elapsed_ms: number;
}
export interface InvestigationRow {
  id: string; mode: Mode; created_at: string; conclusion: string; top_service: string | null;
  fault_class?: string | null; confidence: number | null;
}
export interface EvidencePaths {
  hypothesis_id: string; incident_id: string; service: string;
  supporting: { observation: string; service: string; signal: string; score: number; kind: string; source: string }[];
  contradicting: { observation: string; service: string; signal: string; score: number }[];
  memories: { memory: string; effect: string }[]; symptom_paths: DepPath[];
}
export interface ObservationRecord { observation: Observation & Record<string, unknown>; incident_id: string; service: string; signal_key: string | null }
export interface SimResult {
  outcome: { result: string; detail: string; source: string; side_effects: string[] };
  memory_id: string; duplicate: boolean; conditions?: string[]; contradicts?: string[];
}
export interface MemoryRow {
  id: string; derived_from: string; service: string; action_type: string; outcome: string; lesson: string;
  created_at: string; source?: string; conditions: string[]; contradicts: string[]; incident_source: string;
}
export interface TimelineRow {
  incident_id: string; title: string; source: string; status: string; detected_at: number; investigations: number;
  actions: { action: string; target: string; at: string; outcome: string; memory: string | null; side_effects: string[] | null }[];
}
export type Summary = Record<string, Record<string, number | null>>;
export interface EvalRow {
  incident_id: string; mode: string; truth_root: string; truth_fault: string; predicted: string | null; top1: boolean;
  fault_class_pred: string | null; fault_class_ok?: boolean; action: { type: string; target: string } | null;
  action_outcome: string | null; latency_ms?: number;
}
export interface Evaluation {
  generated_at: string; dataset: Record<string, unknown> & { source?: Record<string, string> };
  test_summary: Summary; validation_summary: Summary; history_summary_development_set: Summary; synthetic_summary: Summary;
  leakage_issues: string[]; integrity_ok: boolean; rows_test: EvalRow[]; rows_validation?: EvalRow[]; rows_synthetic: EvalRow[];
  elapsed_s?: number;
}
