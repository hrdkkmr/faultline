"""Typed graph tools used by the investigation agent.

Each tool validates its input, runs parameterized Cypher against FalkorDB through GraphClient,
and returns a Pydantic model that preserves source IDs and relationship paths. Missing data is
reported explicitly. Nothing is fabricated: no path is returned if the graph has none.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone

from app.graph import queries as Q
from app.graph.client import GraphClient
from app.graph.loader import signal_key
from app.schemas.models import (
    ActionEvaluation,
    ActionSpec,
    BlastRadius,
    BlastRadiusEntry,
    ChangeRecord,
    DependencyPath,
    DependencyTrace,
    EvidencePaths,
    IncidentView,
    MemoryMatch,
    MemoryRetrieval,
    ObservationView,
    OutcomeRecord,
    RecentChanges,
    RelatedIncident,
    RelatedIncidents,
)
from app.simulation.catalog import ACTIONS, RESOURCE_SIGNALS

log = logging.getLogger("faultline.tools")

_ID_RE = re.compile(r"^(INC|SYN)-[A-Za-z0-9_\-]{1,40}$")
_SVC_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,40}$")


class ToolInputError(ValueError):
    pass


class NotFoundError(LookupError):
    pass


def validate_incident_id(incident_id: str) -> str:
    if not isinstance(incident_id, str) or not _ID_RE.match(incident_id):
        raise ToolInputError(f"invalid incident id: {incident_id!r}")
    return incident_id


def validate_service_name(service: str) -> str:
    if not isinstance(service, str) or not _SVC_RE.match(service):
        raise ToolInputError(f"invalid service name: {service!r}")
    return service


def _obs(o: dict, linked: str | None = None) -> ObservationView:
    return ObservationView(
        id=o["id"], kind=o.get("kind"), service=o.get("service"), linked_service=linked,
        signal=o.get("signal"), score=o.get("score", 0.0), direction=o.get("direction"),
        anomalous=bool(o.get("anomalous")), baseline=o.get("baseline"), observed=o.get("observed"),
        onset_s=o.get("onset_s"), caller=o.get("caller"), samples=o.get("samples") or [],
        raw_ref=o.get("raw_ref"), source=o.get("source"),
    )


class GraphTools:
    def __init__(self, client: GraphClient, max_depth: int | None = None):
        self.g = client
        self.max_depth = max_depth or client.settings.max_depth
        self.calls: list[dict] = []  # tool-call log for the investigation trace

    def _log(self, tool: str, args: dict, t0: float, n: int) -> None:
        ms = round((time.perf_counter() - t0) * 1000, 2)
        self.calls.append({"tool": tool, "args": args, "ms": ms, "results": n})
        log.debug("tool", extra={"tool": tool, "ms": ms, "results": n})

    def _require_service(self, service: str) -> None:
        validate_service_name(service)
        if not self.g.ro_query(Q.SERVICE_EXISTS, {"service": service}):
            raise NotFoundError(f"unknown service: {service}")

    def _require_incident(self, incident_id: str) -> dict:
        validate_incident_id(incident_id)
        rows = self.g.ro_query(Q.INCIDENT, {"incident_id": incident_id})
        if not rows:
            raise NotFoundError(f"unknown incident: {incident_id}")
        return rows[0]

    # 1 ---------------------------------------------------------------------------------------
    def trace_dependencies(self, service: str, max_depth: int = 3, direction: str = "downstream") -> DependencyTrace:
        t0 = time.perf_counter()
        self._require_service(service)
        if direction not in ("downstream", "upstream"):
            raise ToolInputError("direction must be 'downstream' or 'upstream'")
        q = Q.with_depth(Q.TRACE_DOWNSTREAM if direction == "downstream" else Q.TRACE_UPSTREAM,
                         max_depth, self.max_depth)
        rows = self.g.ro_query(q, {"service": service})
        paths = [DependencyPath(**r) for r in rows]
        reachable = sorted({p.service for p in paths})
        self._log("trace_dependencies", {"service": service, "max_depth": max_depth, "direction": direction},
                  t0, len(paths))
        return DependencyTrace(service=service, direction=direction, max_depth=max_depth,
                               reachable=reachable, paths=paths)

    # 2 ---------------------------------------------------------------------------------------
    def calculate_blast_radius(self, service: str, incident_id: str | None = None) -> BlastRadius:
        t0 = time.perf_counter()
        self._require_service(service)
        if incident_id:
            self._require_incident(incident_id)
        rows = self.g.ro_query(Q.with_depth(Q.BLAST_RADIUS, self.max_depth, self.max_depth),
                               {"service": service, "incident_id": incident_id or ""})
        entries = [BlastRadiusEntry(service=r["service"], kind=r["kind"], depth=r["depth"],
                                    observed_impact=bool(r["anomalous_observations"]),
                                    evidence=r["anomalous_observations"]) for r in rows]
        self._log("calculate_blast_radius", {"service": service, "incident_id": incident_id}, t0, len(entries))
        return BlastRadius(
            service=service, incident_id=incident_id, entries=entries,
            potential=[e.service for e in entries],
            observed=[e.service for e in entries if e.observed_impact],
            basis="architecture DEPENDS_ON edges (reverse traversal); observed_impact from incident observations",
        )

    # 3 ---------------------------------------------------------------------------------------
    def inspect_incident(self, incident_id: str, only_anomalous: bool = False) -> IncidentView:
        t0 = time.perf_counter()
        row = self._require_incident(incident_id)
        obs_rows = self.g.ro_query(Q.INCIDENT_OBSERVATIONS,
                                   {"incident_id": incident_id, "only_anomalous": only_anomalous})
        inc = row["incident"]
        observations = [_obs(r["observation"], r["linked_service"]) for r in obs_rows]
        self._log("inspect_incident", {"incident_id": incident_id}, t0, len(observations))
        return IncidentView(
            id=inc["id"], title=inc.get("title"), description=inc.get("description"),
            source=inc.get("source"), status=inc.get("status"), system=row.get("system"),
            detected_at=inc.get("detected_at"), detected_at_iso=inc.get("detected_at_iso"),
            telemetry={k: bool(inc.get(f"has_{k}")) for k in ("metrics", "logs", "traces")},
            provenance=inc.get("provenance"), observations=observations,
            anomalous_services=sorted({o.service for o in observations if o.anomalous and o.linked_service}),
        )

    # 4 ---------------------------------------------------------------------------------------
    def find_recent_changes(self, services: list[str], until_ts: int, time_window_s: int = 3600) -> RecentChanges:
        t0 = time.perf_counter()
        if not services:
            raise ToolInputError("at least one service required")
        for s in services:
            validate_service_name(s)
        if not (60 <= time_window_s <= 30 * 86400):
            raise ToolInputError("time_window_s must be between 60 s and 30 days")
        total = self.g.ro_query(Q.COUNT_DEPLOYMENTS)[0]["n"]
        rows = self.g.ro_query(Q.RECENT_CHANGES, {"services": services, "since": until_ts - time_window_s,
                                                  "until": until_ts})
        self._log("find_recent_changes", {"services": services, "window_s": time_window_s}, t0, len(rows))
        return RecentChanges(
            services=services, since=until_ts - time_window_s, until=until_ts,
            changes=[ChangeRecord(**r) for r in rows],
            data_available=total > 0,
            note=None if total else "No Deployment records exist in the graph (RCAEval provides no change data).",
        )

    # 5 ---------------------------------------------------------------------------------------
    def retrieve_related_incidents(self, incident_id: str, limit: int = 5,
                                   allowed_ids: list[str] | None = None) -> RelatedIncidents:
        t0 = time.perf_counter()
        self._require_incident(incident_id)
        if not 1 <= limit <= 50:
            raise ToolInputError("limit must be in [1, 50]")
        rows = self.g.ro_query(Q.RELATED_INCIDENTS, {"incident_id": incident_id, "limit": limit,
                                                     "allowed": allowed_ids or []})
        self._log("retrieve_related_incidents", {"incident_id": incident_id}, t0, len(rows))
        return RelatedIncidents(incident_id=incident_id,
                                related=[RelatedIncident(**r) for r in rows],
                                basis="shared anomalous Signal nodes (Jaccard over service|signal|direction)")

    # 6 ---------------------------------------------------------------------------------------
    def retrieve_evidence_paths(self, hypothesis_id: str) -> EvidencePaths:
        t0 = time.perf_counter()
        if not isinstance(hypothesis_id, str) or not re.match(r"^HYP-[A-Za-z0-9_\-:.]{1,120}$", hypothesis_id):
            raise ToolInputError(f"invalid hypothesis id: {hypothesis_id!r}")
        rows = self.g.ro_query(Q.HYPOTHESIS_EVIDENCE, {"hypothesis_id": hypothesis_id})
        if not rows:
            raise NotFoundError(f"unknown hypothesis: {hypothesis_id}")
        r = rows[0]
        h = r["hypothesis"]
        paths = self.g.ro_query(Q.with_depth(Q.SYMPTOM_PATHS, 4, self.max_depth),
                                {"incident_id": h["incident_id"], "service": r["service"]})
        self._log("retrieve_evidence_paths", {"hypothesis_id": hypothesis_id}, t0, len(paths))
        return EvidencePaths(
            hypothesis_id=hypothesis_id, incident_id=h["incident_id"], service=r["service"],
            supporting=[x for x in r["support"] if x], contradicting=[x for x in r["contra"] if x],
            memories=[x for x in r["memories"] if x],
            symptom_paths=[DependencyPath(service=p["from_service"], depth=p["depth"], path=p["path"],
                                          rel_types=p["rel_types"], rel_sources=p["rel_sources"]) for p in paths],
        )

    # 7 ---------------------------------------------------------------------------------------
    def retrieve_applicable_memories(self, incident_id: str, allowed_sources: list[str] | None = None,
                                     limit: int = 20) -> MemoryRetrieval:
        """Memories are applicable only if their required conditions hold in THIS incident."""
        t0 = time.perf_counter()
        self._require_incident(incident_id)
        anomalous = self.g.ro_query(Q.ANOMALOUS_SIGNALS_OF_INCIDENT, {"incident_id": incident_id})
        present = {r["key"]: r["observation"] for r in anomalous}
        anomalous_services = sorted({k.split("|")[0] for k in present})
        rows = self.g.ro_query(Q.APPLICABLE_MEMORIES, {
            "incident_id": incident_id, "allowed_sources": allowed_sources or [],
            "anomalous_services": anomalous_services, "limit": limit})
        matches = []
        for r in rows:
            m = r["memory"]
            required, matched = r["required"], r["matched"]
            missing = sorted(set(required) - set(matched))
            coverage = len(matched) / max(1, len(required))
            reasons = []
            if coverage >= 0.999:
                verdict = "applicable"
            elif coverage >= 0.5:
                verdict = "partial"
                reasons.append(f"{len(missing)} of {len(required)} required conditions absent: {missing}")
            else:
                verdict = "rejected"
                reasons.append(f"required conditions absent: {missing}")
            # Contradicting signals: a memory about target T assumed T was locally anomalous.
            if m.get("service") not in anomalous_services:
                verdict = "rejected"
                reasons.append(f"memory target {m.get('service')} shows no anomaly in this incident")
            if m.get("requires_deployment"):
                ch = self.g.ro_query(Q.RECENT_CHANGES, {"services": [m["service"]],
                                                        "since": 0, "until": 2**62})
                inc = self._require_incident(incident_id)["incident"]
                recent = [c for c in ch if 0 <= inc["detected_at"] - c["at"] <= 3600]
                if not recent:
                    verdict = "rejected"
                    reasons.append(f"memory required a recent deployment of {m['service']}; none found")
            if r["contradicted_by"]:
                reasons.append(f"conflicting outcomes recorded in {r['contradicted_by']}")
                if verdict == "applicable":
                    verdict = "partial"
            matches.append(MemoryMatch(
                memory_id=m["id"], derived_from=m.get("derived_from"), service=m.get("service"),
                action_type=m.get("action_type"), outcome=m.get("outcome"), lesson=m.get("lesson"),
                required_conditions=required, matched_conditions=matched, missing_conditions=missing,
                matched_observations=[present[k] for k in matched if k in present],
                source_similarity=round(r["source_similarity"], 3),
                coverage=round(coverage, 3), verdict=verdict, reasons=reasons,
                contradicted_by=r["contradicted_by"], created_at=m.get("created_at"),
            ))
        self._log("retrieve_applicable_memories", {"incident_id": incident_id}, t0, len(matches))
        return MemoryRetrieval(incident_id=incident_id, matches=matches,
                               basis="Memory-[:APPLIES_UNDER]->Signal<-[:OF_SIGNAL]-Observation<-Incident")

    # 8 ---------------------------------------------------------------------------------------
    def evaluate_candidate_action(self, action: ActionSpec, incident_id: str,
                                  memories: MemoryRetrieval | None = None) -> ActionEvaluation:
        """Check an action's preconditions against graph evidence of THIS incident."""
        t0 = time.perf_counter()
        inc = self._require_incident(incident_id)["incident"]
        if action.type not in ACTIONS:
            raise ToolInputError(f"unknown action type {action.type!r}")
        spec = ACTIONS[action.type]
        reasons, evidence, blockers = [], [], []

        if action.type == "gather_more_evidence":
            self._log("evaluate_candidate_action", action.model_dump(), t0, 0)
            return ActionEvaluation(action=action, verdict="recommended", risk=spec.risk,
                                    requires_approval=False, reasons=["read-only; always safe"],
                                    evidence=[], blockers=[], memory_effect=0.0)

        self._require_service(action.target)
        own = self.g.ro_query(Q.SERVICE_ANOMALIES_IN_INCIDENT, {"incident_id": incident_id, "service": action.target})
        own_sigs = {(o["signal"], o["direction"]) for o in own}
        if not own:
            blockers.append(f"{action.target} shows no anomalous observation in this incident")
        matched_pre = [o for o in own if (o["signal"], o["direction"]) in spec.supporting_signals]
        if spec.supporting_signals and own and not matched_pre:
            blockers.append(f"{action.type} requires one of {sorted(s for s, _ in spec.supporting_signals)} "
                            f"anomalous on {action.target}; observed {sorted(s for s, _ in own_sigs)}")
        evidence += [o["id"] for o in matched_pre]
        if matched_pre:
            reasons.append(f"precondition met by {[o['signal'] for o in matched_pre]} on {action.target}")

        if spec.requires_deployment:
            ch = self.find_recent_changes([action.target], until_ts=inc["detected_at"], time_window_s=3600)
            if not ch.changes:
                blockers.append(f"no deployment of {action.target} in the hour before detection"
                                + ("" if ch.data_available else " (no change data in this source)"))
            else:
                evidence += [c.id for c in ch.changes]
                reasons.append(f"recent change {ch.changes[0].id} on {action.target}")

        if action.type == "scale_out":
            # Scaling the victim does not help if a dependency it waits on is the bottleneck.
            deps = self.g.ro_query(Q.ANOMALOUS_DEPENDENCIES, {"incident_id": incident_id, "service": action.target})
            local_res = [o for o in own if o["signal"] in RESOURCE_SIGNALS and o["direction"] == "up"]
            if deps and not local_res:
                blockers.append(f"{action.target} has no local resource saturation while dependencies "
                                f"{[d['service'] for d in deps]} are anomalous; scaling it is unlikely to help")

        # Net memory effect = strongest matching success - strongest matching failure (max, not sum, so an
        # action that merely happened to be tried often does not outvote a more relevant memory).
        best_pos = best_neg = 0.0
        for m in (memories.matches if memories else []):
            if m.service != action.target or m.action_type != action.type or m.verdict == "rejected":
                continue
            w = m.coverage * (1.0 if m.verdict == "applicable" else 0.5)
            if m.outcome == "resolved":
                best_pos = max(best_pos, w)
                reasons.append(f"memory {m.memory_id}: same action resolved a matching incident ({m.derived_from})")
            else:
                best_neg = max(best_neg, w)
                reasons.append(f"memory {m.memory_id}: same action previously {m.outcome} under matching conditions")
            evidence.append(m.memory_id)
        memory_effect = best_pos - best_neg

        if blockers:
            verdict = "not_recommended"
        elif memory_effect < 0:
            verdict = "not_recommended"
            blockers.append("prior attempts of this action under matching conditions did not resolve the incident")
        else:
            verdict = "recommended"
        self._log("evaluate_candidate_action", action.model_dump(), t0, len(evidence))
        return ActionEvaluation(action=action, verdict=verdict, risk=spec.risk,
                                requires_approval=spec.requires_approval, reasons=reasons,
                                evidence=evidence, blockers=blockers, memory_effect=round(memory_effect, 3))

    # 9 ---------------------------------------------------------------------------------------
    def record_incident_outcome(self, incident_id: str, action: ActionSpec, outcome: OutcomeRecord,
                                idempotency_key: str | None = None,
                                conditions: list[str] | None = None) -> dict:
        """Persist an executed action, its outcome, and a Memory episode. Idempotent per key.

        Memory conditions are the anomalous Signal keys on the action target (plus, if given,
        explicit extra conditions). Contradicting earlier memories are linked, never overwritten.
        """
        t0 = time.perf_counter()
        inc = self._require_incident(incident_id)["incident"]
        if action.type not in ACTIONS or action.type == "gather_more_evidence":
            raise ToolInputError(f"cannot record outcome for action type {action.type!r}")
        self._require_service(action.target)
        if outcome.result not in ("resolved", "not_resolved", "worsened"):
            raise ToolInputError("outcome.result must be resolved | not_resolved | worsened")
        key = idempotency_key or "default"
        attempt = hashlib.sha1(f"{incident_id}|{action.type}|{action.target}|{key}".encode()).hexdigest()[:12]
        action_id, outcome_id, memory_id = f"ACT-{attempt}", f"OUT-{attempt}", f"MEM-{attempt}"

        existing = self.g.ro_query("MATCH (m:Memory {id: $id}) RETURN m.id AS id", {"id": memory_id})
        if existing:
            self._log("record_incident_outcome", {"incident_id": incident_id, "dedup": True}, t0, 0)
            return {"action_id": action_id, "outcome_id": outcome_id, "memory_id": memory_id, "duplicate": True}

        own = self.g.ro_query(Q.SERVICE_ANOMALIES_IN_INCIDENT, {"incident_id": incident_id, "service": action.target})
        conds = sorted({signal_key(action.target, o["signal"], o["direction"]) for o in own
                        if o["kind"] in ("metric", "log", "trace")} | set(conditions or []))
        if not conds:
            raise ToolInputError(f"refusing to store a memory without conditions: {action.target} has no "
                                 f"anomalous signals in {incident_id}")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        spec = ACTIONS[action.type]
        lesson = (f"{action.type} on {action.target} {outcome.result.replace('_', ' ')} an incident whose "
                  f"{action.target} signals were {', '.join(c.split('|', 1)[1] for c in conds)}")
        self.g.query(
            """
            MATCH (i:Incident {id: $inc}), (s:Service {name: $target})
            MERGE (a:Action {id: $aid})
            SET a.type = $type, a.target = $target, a.status = 'executed', a.params = $params,
                a.risk = $risk, a.executed_at = $now, a.mode = 'simulated'
            MERGE (i)-[:ATTEMPTED]->(a)
            MERGE (a)-[:TARGETS]->(s)
            MERGE (o:Outcome {id: $oid})
            SET o.result = $result, o.detail = $detail, o.source = $osrc, o.at = $now,
                o.side_effects = $side
            MERGE (a)-[:PRODUCED]->(o)
            MERGE (m:Memory {id: $mid})
            SET m.derived_from = $inc, m.service = $target, m.action_type = $type, m.outcome = $result,
                m.lesson = $lesson, m.created_at = $now, m.version = 1, m.source = $osrc,
                m.incident_source = $isrc, m.requires_deployment = $req_dep
            MERGE (m)-[:DERIVED_FROM]->(o)
            MERGE (m)-[:ABOUT]->(s)
            SET i.status = CASE WHEN $result = 'resolved' THEN 'resolved' ELSE 'mitigation_failed' END
            """,
            {"inc": incident_id, "target": action.target, "aid": action_id, "type": action.type,
             "params": json.dumps(action.params, sort_keys=True), "risk": spec.risk, "now": now,
             "oid": outcome_id, "result": outcome.result, "detail": outcome.detail or "",
             "osrc": outcome.source, "side": outcome.side_effects, "mid": memory_id, "lesson": lesson,
             "isrc": inc.get("source"), "req_dep": spec.requires_deployment},
        )
        self.g.query(
            """
            MATCH (m:Memory {id: $mid})
            UNWIND $conds AS k
            MERGE (g:Signal {key: k})
            ON CREATE SET g.service = split(k, '|')[0], g.signal = split(k, '|')[1], g.direction = split(k, '|')[2]
            MERGE (m)-[:APPLIES_UNDER]->(g)
            """,
            {"mid": memory_id, "conds": conds},
        )
        # Contradiction: same target+action, overlapping conditions, different outcome.
        contra = self.g.query(
            """
            MATCH (m:Memory {id: $mid})-[:APPLIES_UNDER]->(g:Signal)<-[:APPLIES_UNDER]-(o:Memory)
            WHERE o.id <> m.id AND o.service = m.service AND o.action_type = m.action_type
                  AND o.outcome <> m.outcome
            WITH m, o, count(g) AS shared
            WHERE shared >= 1
            MERGE (m)-[c:CONTRADICTS]->(o)
            SET c.shared_conditions = shared, c.at = $now
            RETURN collect(o.id) AS ids
            """,
            {"mid": memory_id, "now": now},
        )
        self._log("record_incident_outcome", {"incident_id": incident_id, "action": action.type}, t0, 1)
        return {"action_id": action_id, "outcome_id": outcome_id, "memory_id": memory_id, "duplicate": False,
                "conditions": conds, "contradicts": contra[0]["ids"] if contra else []}
