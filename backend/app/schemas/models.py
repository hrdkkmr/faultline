"""Typed tool inputs/outputs and the investigation report schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ObservationView(BaseModel):
    id: str
    kind: str | None = None
    service: str | None = None
    linked_service: str | None = None
    signal: str | None = None
    score: float = 0.0
    direction: str | None = None
    anomalous: bool = False
    baseline: float | None = None
    observed: float | None = None
    onset_s: int | None = None
    caller: str | None = None
    samples: list[str] = Field(default_factory=list)
    raw_ref: str | None = None
    source: str | None = None


class IncidentView(BaseModel):
    id: str
    title: str | None = None
    description: str | None = None
    source: str | None = None
    status: str | None = None
    system: str | None = None
    detected_at: int | None = None
    detected_at_iso: str | None = None
    telemetry: dict[str, bool] = Field(default_factory=dict)
    provenance: str | None = None
    observations: list[ObservationView] = Field(default_factory=list)
    anomalous_services: list[str] = Field(default_factory=list)


class DependencyPath(BaseModel):
    service: str
    depth: int
    path: list[str]
    rel_types: list[str]
    rel_sources: list[str | None]


class DependencyTrace(BaseModel):
    service: str
    direction: str
    max_depth: int
    reachable: list[str]
    paths: list[DependencyPath]


class BlastRadiusEntry(BaseModel):
    service: str
    kind: str | None = None
    depth: int
    observed_impact: bool
    evidence: list[str] = Field(default_factory=list)


class BlastRadius(BaseModel):
    service: str
    incident_id: str | None
    entries: list[BlastRadiusEntry]
    potential: list[str]
    observed: list[str]
    basis: str


class ChangeRecord(BaseModel):
    id: str
    service: str
    version: str | None = None
    previous_version: str | None = None
    at: int
    change_type: str | None = None
    description: str | None = None
    source: str | None = None


class RecentChanges(BaseModel):
    services: list[str]
    since: int
    until: int
    changes: list[ChangeRecord]
    data_available: bool
    note: str | None = None


class RelatedIncident(BaseModel):
    incident_id: str
    title: str | None = None
    source: str | None = None
    shared: list[str]
    jaccard: float


class RelatedIncidents(BaseModel):
    incident_id: str
    related: list[RelatedIncident]
    basis: str


class EvidencePaths(BaseModel):
    hypothesis_id: str
    incident_id: str
    service: str
    supporting: list[dict]
    contradicting: list[dict]
    memories: list[dict]
    symptom_paths: list[DependencyPath]


class MemoryMatch(BaseModel):
    memory_id: str
    derived_from: str | None
    service: str | None
    action_type: str | None
    outcome: str | None
    lesson: str | None
    required_conditions: list[str]
    matched_conditions: list[str]
    missing_conditions: list[str]
    matched_observations: list[str]
    source_similarity: float = 0.0
    coverage: float
    verdict: Literal["applicable", "partial", "rejected"]
    reasons: list[str]
    contradicted_by: list[str] = Field(default_factory=list)
    created_at: str | None = None


class MemoryRetrieval(BaseModel):
    incident_id: str
    matches: list[MemoryMatch]
    basis: str


class ActionSpec(BaseModel):
    type: str = Field(min_length=1, max_length=40, pattern=r"^[a-z_]+$")
    target: str = Field(default="", max_length=41)
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)


class ActionEvaluation(BaseModel):
    action: ActionSpec
    verdict: Literal["recommended", "not_recommended", "needs_more_evidence"]
    risk: str
    requires_approval: bool
    reasons: list[str]
    evidence: list[str]
    blockers: list[str]
    memory_effect: float = 0.0


class OutcomeRecord(BaseModel):
    result: Literal["resolved", "not_resolved", "worsened"]
    detail: str | None = None
    source: Literal["simulator", "operator"] = "simulator"
    side_effects: list[str] = Field(default_factory=list)


# ---- investigation report ------------------------------------------------------------------

class ScoreBreakdown(BaseModel):
    local_evidence: float
    coverage: float = 0.0
    memory: float = 0.0
    total: float


class HypothesisView(BaseModel):
    id: str
    rank: int
    service: str
    fault_class: str
    fault_class_basis: str
    status: Literal["hypothesis"] = "hypothesis"
    score: ScoreBreakdown
    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    explained_services: list[str]
    graph_paths: list[DependencyPath]
    memories: list[str]
    rationale: list[str]


class MitigationView(BaseModel):
    action: ActionSpec
    addresses_hypothesis: str
    verdict: str
    risk: str
    requires_approval: bool
    preconditions_met: list[str]
    blockers: list[str]
    evidence: list[str]
    memory_effect: float


class InvestigationReport(BaseModel):
    investigation_id: str
    incident_id: str
    mode: Literal["A_incident_only", "B_graph", "C_graph_memory"]
    conclusion: Literal["root_cause_hypothesis", "inconclusive"]
    suspected_root_cause: str | None
    suspected_fault_class: str | None
    confidence: float = Field(description="score share of the top hypothesis among candidates (ranking, not probability)")
    hypotheses: list[HypothesisView]
    affected_services: dict
    candidate_mitigations: list[MitigationView]
    related_incidents: list[dict]
    memories_considered: list[MemoryMatch]
    recent_changes: dict
    missing_information: list[str]
    human_approval_required: bool
    tool_calls: list[dict]
    narrative: str | None = None
    narrative_source: str = "deterministic"
    created_at: str
    elapsed_ms: float
