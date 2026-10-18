"""Investigation orchestrator.

Workflow (each step is a typed graph tool call, recorded in `tool_calls`):
 1. inspect_incident                 -> observations from the graph
 2. (B, C) dependency reachability among anomalous services (Cypher)
 3. (B, C) find_recent_changes, retrieve_related_incidents
 4. (C) retrieve_applicable_memories
 5. score + rank hypotheses (app.agents.ranking), infer fault class
 6. evidence for/against each hypothesis, graph paths
 7. blast radius of the top hypothesis
 8. candidate mitigations, each validated by evaluate_candidate_action
 9. abstain ("inconclusive") when evidence is weak
10. optionally persist Investigation / Hypothesis / proposed Action nodes
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone

from app.agents import ranking
from app.agents.narrator import Narrator, NullNarrator
from app.agents.tools import GraphTools
from app.graph import queries as Q
from app.schemas.models import (
    ActionSpec,
    DependencyPath,
    HypothesisView,
    InvestigationReport,
    MemoryRetrieval,
    MitigationView,
    ScoreBreakdown,
)
from app.simulation.catalog import ACTIONS, RESOURCE_SIGNALS, RISK_ORDER

log = logging.getLogger("faultline.investigator")

MODES = ("A_incident_only", "B_graph", "C_graph_memory")
MAX_HYPOTHESES = 5


class Investigator:
    def __init__(self, tools: GraphTools, narrator: Narrator | None = None):
        self.tools = tools
        self.g = tools.g
        self.narrator = narrator or NullNarrator()

    def investigate(self, incident_id: str, mode: str = "C_graph_memory", persist: bool = False,
                    memory_sources: list[str] | None = None, related_allowed: list[str] | None = None,
                    narrate: bool = False) -> InvestigationReport:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        t0 = time.perf_counter()
        self.tools.calls = []
        use_graph = mode != "A_incident_only"
        missing: list[str] = []

        incident = self.tools.inspect_incident(incident_id)
        obs = [o.model_dump() for o in incident.observations]
        for k, v in incident.telemetry.items():
            if not v:
                missing.append(f"no {k} telemetry for this incident")
        cands = ranking.build_candidates(obs)

        paths: list[dict] = []
        changes = None
        related: list[dict] = []
        memories = MemoryRetrieval(incident_id=incident_id, matches=[], basis="not used in this mode")
        if use_graph and cands:
            t1 = time.perf_counter()
            paths = self.g.ro_query(Q.with_depth(Q.ANOMALY_SUBGRAPH_PATHS, 4, self.tools.max_depth),
                                    {"services": sorted(cands)})
            self.tools.calls.append({"tool": "anomaly_subgraph_paths", "args": {"services": sorted(cands)},
                                     "ms": round((time.perf_counter() - t1) * 1000, 2), "results": len(paths)})
            ranking.apply_coverage(cands, paths)
            changes = self.tools.find_recent_changes(sorted(cands), until_ts=incident.detected_at or 0,
                                                     time_window_s=3600)
            if not changes.data_available:
                missing.append("no deployment/change records available for this data source")
            ranking.apply_deployments(cands, {c.service for c in changes.changes})
            related = [r.model_dump() for r in
                       self.tools.retrieve_related_incidents(incident_id, limit=5, allowed_ids=related_allowed).related]
        if mode == "C_graph_memory" and cands:
            memories = self.tools.retrieve_applicable_memories(incident_id, allowed_sources=memory_sources)
            ranking.apply_memory(cands, memories.matches)

        ranked = ranking.rank(cands, mode)[:MAX_HYPOTHESES]
        stamp = datetime.now(timezone.utc)
        inv_id = "INV-" + hashlib.sha1(f"{incident_id}|{mode}|{stamp.isoformat()}".encode()).hexdigest()[:12]

        hyps: list[HypothesisView] = []
        for i, c in enumerate(ranked, start=1):
            fc, basis = ranking.fault_class(c)
            support = [o["id"] for o in sorted(c.observations, key=lambda o: -o["score"])[:6]]
            contra, rationale = self._contradictions(incident_id, c, cands, use_graph)
            rationale = self._rationale(c, mode, len(cands)) + rationale
            hyps.append(HypothesisView(
                id=f"HYP-{inv_id[4:]}-{i}", rank=i, service=c.service, fault_class=fc, fault_class_basis=basis,
                score=ScoreBreakdown(local_evidence=round(c.local, 4), coverage=round(c.coverage, 4),
                                     memory=round(c.memory, 4), total=c.total),
                supporting_evidence=support, contradicting_evidence=contra,
                explained_services=c.explained if use_graph else [],
                graph_paths=[DependencyPath(service=p["explains"], depth=p["depth"], path=p["path"],
                                            rel_types=p["rel_types"], rel_sources=p["rel_sources"])
                             for p in c.explained_paths] if use_graph else [],
                memories=c.memories, rationale=rationale,
            ))

        top = hyps[0] if hyps else None
        conclusive = bool(top) and ranked[0].local >= ranking.INCONCLUSIVE_BELOW
        if not hyps:
            missing.append("no anomalous observations linked to known services")
        elif not conclusive:
            missing.append(f"strongest evidence is weak (local {ranked[0].local:.2f} < {ranking.INCONCLUSIVE_BELOW})")
        total_score = sum(h.score.total for h in hyps) or 1.0
        confidence = round(top.score.total / total_score, 3) if top else 0.0

        affected = {"basis": "none"}
        if top and use_graph:
            br = self.tools.calculate_blast_radius(top.service, incident_id)
            affected = {"root": top.service, "potential": br.potential, "observed": br.observed,
                        "entries": [e.model_dump() for e in br.entries], "basis": br.basis}
        elif top:
            affected = {"root": top.service, "potential": [], "observed": incident.anomalous_services,
                        "entries": [], "basis": "anomalous services in this incident (no graph in mode A)"}

        mitigations = self._mitigations(incident_id, hyps, cands, memories, conclusive, use_graph)

        report = InvestigationReport(
            investigation_id=inv_id, incident_id=incident_id, mode=mode,
            conclusion="root_cause_hypothesis" if conclusive else "inconclusive",
            suspected_root_cause=top.service if conclusive else None,
            suspected_fault_class=top.fault_class if conclusive else None,
            confidence=confidence if conclusive else 0.0,
            hypotheses=hyps, affected_services=affected, candidate_mitigations=mitigations,
            related_incidents=related, memories_considered=memories.matches,
            recent_changes=changes.model_dump() if changes else {"note": "not used in this mode"},
            missing_information=missing,
            human_approval_required=any(m.requires_approval and m.verdict == "recommended" for m in mitigations),
            tool_calls=list(self.tools.calls), created_at=stamp.isoformat(timespec="seconds"),
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 2),
        )
        if narrate:
            report.narrative, report.narrative_source = self.narrator.narrate(report)
        if persist:
            self._persist(report)
        return report

    # -- helpers ------------------------------------------------------------------------------
    def _rationale(self, c: ranking.Candidate, mode: str, n: int) -> list[str]:
        top_obs = sorted(c.observations, key=lambda o: -o["score"])[:3]
        out = [f"local evidence {c.local:.2f}: " + ", ".join(f"{o['signal']} {o['direction']} (z={o['score']:.0f})"
                                                              for o in top_obs)]
        if mode != "A_incident_only" and n > 1:
            out.append(f"explains {len(c.explained)} of {n - 1} other anomalous services "
                       f"(coverage {c.coverage:.2f})" + (f": {', '.join(c.explained)}" if c.explained else ""))
        if c.deploy:
            out.append("deployed within 1h before detection (weak, temporal only)")
        if c.memory:
            out.append(f"supported by resolved memories {c.memories} (+{c.memory:.2f})")
        return out

    def _contradictions(self, incident_id: str, c: ranking.Candidate, cands: dict, use_graph: bool):
        contra, notes = [], []
        if use_graph:
            deps = self.g.ro_query(Q.ANOMALOUS_DEPENDENCIES, {"incident_id": incident_id, "service": c.service})
            for d in deps:
                dc = cands.get(d["service"])
                if dc and dc.resource > 0:
                    contra += d["observations"][:2]
                    notes.append(f"dependency {d['service']} has its own resource anomaly; "
                                 f"{c.service} may be a victim")
        if c.resource == 0:
            normal = self.g.ro_query(
                "MATCH (:Incident {id: $inc})-[:HAS_OBSERVATION]->(o:Observation {anomalous: false})"
                "-[:OBSERVED_ON]->(:Service {name: $svc}) WHERE o.signal IN $res "
                "RETURN o.id AS id ORDER BY o.signal LIMIT 3",
                {"inc": incident_id, "svc": c.service, "res": sorted(RESOURCE_SIGNALS)})
            if normal:
                contra += [r["id"] for r in normal]
                notes.append(f"no local resource anomaly on {c.service} (resource metrics within baseline)")
        return contra, notes

    def _mitigations(self, incident_id, hyps, cands, memories, conclusive, use_graph) -> list[MitigationView]:
        if not hyps or not conclusive:
            ev = self.tools.evaluate_candidate_action(ActionSpec(type="gather_more_evidence"), incident_id)
            return [MitigationView(action=ev.action, addresses_hypothesis=hyps[0].id if hyps else "",
                                   verdict=ev.verdict, risk=ev.risk, requires_approval=False,
                                   preconditions_met=ev.reasons, blockers=[], evidence=[], memory_effect=0.0)]
        out: list[MitigationView] = []
        # Top hypothesis, plus the runner-up when it is close.
        targets = [hyps[0]] + [h for h in hyps[1:2] if h.score.total >= 0.85 * hyps[0].score.total]
        for h in targets:
            for atype, spec in ACTIONS.items():
                if atype == "gather_more_evidence":
                    continue
                a = ActionSpec(type=atype, target=h.service)
                if use_graph:
                    ev = self.tools.evaluate_candidate_action(a, incident_id, memories)
                else:
                    ev = self._evaluate_local(a, cands.get(h.service))
                out.append(MitigationView(
                    action=a, addresses_hypothesis=h.id, verdict=ev.verdict, risk=ev.risk,
                    requires_approval=ev.requires_approval, preconditions_met=ev.reasons,
                    blockers=ev.blockers, evidence=ev.evidence, memory_effect=ev.memory_effect))
        cls = {h.id: h.fault_class for h in hyps}
        rank_of = {h.id: h.rank for h in hyps}

        def key(m: MitigationView):
            addresses = cls.get(m.addresses_hypothesis) in ACTIONS[m.action.type].addresses
            return (m.verdict != "recommended", rank_of.get(m.addresses_hypothesis, 9), -m.memory_effect,
                    not addresses, RISK_ORDER[m.risk], m.action.type)

        out.sort(key=key)
        if not any(m.verdict == "recommended" for m in out):
            ev = self.tools.evaluate_candidate_action(ActionSpec(type="gather_more_evidence"), incident_id)
            out.insert(0, MitigationView(action=ev.action, addresses_hypothesis=hyps[0].id, verdict="recommended",
                                         risk="none", requires_approval=False,
                                         preconditions_met=["no remediation passed its preconditions"],
                                         blockers=[], evidence=[], memory_effect=0.0))
        return out

    @staticmethod
    def _evaluate_local(a: ActionSpec, c: ranking.Candidate | None):
        """Mode A: preconditions from the target's own observations only (no graph context, no memory)."""
        from app.schemas.models import ActionEvaluation

        spec = ACTIONS[a.type]
        obs = c.observations if c else []
        met = [o for o in obs if (o["signal"], o["direction"]) in spec.supporting_signals]
        blockers = []
        if not obs:
            blockers.append(f"{a.target} has no anomalous observation")
        elif spec.supporting_signals and not met:
            blockers.append(f"no supporting signal for {a.type} on {a.target}")
        if spec.requires_deployment:
            blockers.append("deployment history not consulted in incident-only mode")
        return ActionEvaluation(action=a, verdict="not_recommended" if blockers else "recommended",
                                risk=spec.risk, requires_approval=spec.requires_approval,
                                reasons=[f"precondition met by {[o['signal'] for o in met]}"] if met else [],
                                evidence=[o["id"] for o in met], blockers=blockers)

    def _persist(self, r: InvestigationReport) -> None:
        self.g.query(
            """
            MATCH (i:Incident {id: $inc})
            MERGE (v:Investigation {id: $id})
            SET v.mode = $mode, v.created_at = $at, v.conclusion = $conclusion, v.top_service = $top,
                v.fault_class = $fc, v.confidence = $conf, v.elapsed_ms = $ms, v.incident_id = $inc,
                v.report = $report
            MERGE (v)-[:INVESTIGATED]->(i)
            SET i.status = CASE WHEN i.status = 'open' THEN 'investigated' ELSE i.status END
            """,
            {"inc": r.incident_id, "id": r.investigation_id, "mode": r.mode, "at": r.created_at,
             "conclusion": r.conclusion, "top": r.suspected_root_cause or "", "fc": r.suspected_fault_class or "",
             "conf": r.confidence, "ms": r.elapsed_ms, "report": r.model_dump_json()},
        )
        for h in r.hypotheses:
            self.g.query(
                """
                MATCH (v:Investigation {id: $inv}), (s:Service {name: $svc})
                MERGE (h:Hypothesis {id: $id})
                SET h.rank = $rank, h.service = $svc, h.fault_class = $fc, h.score = $score,
                    h.incident_id = $inc, h.status = 'hypothesis'
                MERGE (v)-[:PROPOSED]->(h)
                MERGE (h)-[:ABOUT]->(s)
                WITH h
                UNWIND $support AS oid
                MATCH (o:Observation {id: oid})
                MERGE (h)-[:SUPPORTED_BY]->(o)
                """,
                {"inv": r.investigation_id, "svc": h.service, "id": h.id, "rank": h.rank, "fc": h.fault_class,
                 "score": h.score.total, "inc": r.incident_id, "support": h.supporting_evidence},
            )
            if h.contradicting_evidence:
                self.g.query("MATCH (h:Hypothesis {id: $id}) UNWIND $ids AS oid MATCH (o:Observation {id: oid}) "
                             "MERGE (h)-[:CONTRADICTED_BY]->(o)", {"id": h.id, "ids": h.contradicting_evidence})
            if h.memories:
                self.g.query("MATCH (h:Hypothesis {id: $id}) UNWIND $ids AS mid MATCH (m:Memory {id: mid}) "
                             "MERGE (h)-[:INFORMED_BY {effect: 'support'}]->(m)", {"id": h.id, "ids": h.memories})
        for k, m in enumerate([m for m in r.candidate_mitigations if m.verdict == "recommended"][:3]):
            if m.action.type == "gather_more_evidence":
                continue
            pid = f"PRO-{r.investigation_id[4:]}-{k}"
            self.g.query(
                """
                MATCH (v:Investigation {id: $inv}), (h:Hypothesis {id: $hid}), (s:Service {name: $target})
                MERGE (a:Action {id: $id})
                SET a.type = $type, a.target = $target, a.status = 'proposed', a.risk = $risk,
                    a.requires_approval = $appr, a.params = $params
                MERGE (v)-[:RECOMMENDED {rank: $rank}]->(a)
                MERGE (a)-[:ADDRESSES]->(h)
                MERGE (a)-[:TARGETS]->(s)
                """,
                {"inv": r.investigation_id, "hid": m.addresses_hypothesis, "target": m.action.target, "id": pid,
                 "type": m.action.type, "risk": m.risk, "appr": m.requires_approval,
                 "params": json.dumps(m.action.params), "rank": k + 1},
            )
