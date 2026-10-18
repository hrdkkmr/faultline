"""Reproducible ablation harness: A (incident only) vs B (graph) vs C (graph + persistent memory).

Leakage controls:
- The agent reads only the graph. Ground truth is loaded here, AFTER each prediction, for scoring.
- Held-out cases never write memory; mode C may only read memories derived from history incidents.
- Each held-out report is scanned for the case name and label keys.

Protocol (RCAEval RE2-OB):
 1. Fresh evaluation graph (default name `faultline_eval`), loaded from data/processed + scenarios.
 2. Memory phase (repetitions 1 and 2, chronological): C-mode investigation using memory from EARLIER history
    incidents only; the top recommended action is applied to the simulator (approved, simulated);
    if it fails, the next recommended action is tried once. Every outcome is stored as Memory.
 3. Held-out phases: VALIDATION = repetition 2 (memory from rep 1), TEST = repetition 3 (memory from reps 1+2).
    The memory phase in step 2 runs over reps 1 and 2 chronologically. A, B, C and C-LOSO run on the
    same cases, with no memory writes.
    C-LOSO (control) restricts memory to history incidents whose root-cause service differs from the
    case's, measuring harm from non-matching memories. This selection uses labels on the EVALUATION
    side only, to define the experiment; the agent never sees them.
 4. Synthetic scenarios: run chronologically with memory accumulation for C.
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from app.agents.investigator import Investigator
from app.agents.tools import GraphTools
from app.config import Settings
from app.graph.client import GraphClient
from app.graph.integrity import check_integrity
from app.graph.loader import load_all
from app.memory.service import execute_simulated_action
from app.schemas.models import InvestigationReport
from app.simulation.scenarios import load_truth
from app.simulation.simulator import Simulator

FAULT_CLASS = {"cpu": "cpu", "mem": "memory", "disk": "disk", "socket": "socket", "delay": "network",
               "loss": "network", "deployment_regression": "deployment_regression"}
MODES = ["A_incident_only", "B_graph", "C_graph_memory"]


def avg_at_k(ranked: list[str], truth: str, k: int = 5) -> float:
    """RCAEval's Avg@k: mean over j=1..k of 1[truth in top-j]."""
    return sum(truth in ranked[:j] for j in range(1, k + 1)) / k


def prf(pred: set, ref: set) -> tuple[float, float]:
    if not pred and not ref:
        return 1.0, 1.0
    p = len(pred & ref) / len(pred) if pred else 0.0
    r = len(pred & ref) / len(ref) if ref else 0.0
    return p, r


class Evaluator:
    def __init__(self, settings: Settings, graph_name: str = "faultline_eval"):
        self.s = settings
        self.client = GraphClient(settings, graph_name=graph_name)
        self.tools = GraphTools(self.client)
        self.inv = Investigator(self.tools)
        self.sim = Simulator(settings.data_path)
        d = settings.data_path
        self.labels = json.loads((d / "eval" / "rcaeval_labels.json").read_text(encoding="utf-8"))
        self.manifest = json.loads((d / "manifests" / "rcaeval_manifest.json").read_text(encoding="utf-8"))
        self.case_of = {c["incident_id"]: c["case"] for c in self.manifest["cases"]}
        self.split = {c["incident_id"]: c["split"] for c in self.manifest["cases"]}
        self.syn_truth = load_truth(d)

    # -- setup --------------------------------------------------------------------------------
    def reset_graph(self) -> dict:
        return load_all(self.s, reset=True, client=self.client)

    def _detected(self, ids: list[str]) -> list[str]:
        rows = self.client.ro_query("MATCH (i:Incident) WHERE i.id IN $ids RETURN i.id AS id, i.detected_at AS t",
                                    {"ids": ids})
        return [r["id"] for r in sorted(rows, key=lambda r: (r["t"], r["id"]))]

    def _reference_affected(self, root: str) -> set[str]:
        return set(self.tools.calculate_blast_radius(root).potential)

    # -- scoring ------------------------------------------------------------------------------
    def score(self, r: InvestigationReport, truth_root: str, truth_fault: str, simulate: bool = True) -> dict:
        ranked = [h.service for h in r.hypotheses]
        pred = r.suspected_root_cause
        cited = sorted({i for h in r.hypotheses for i in h.supporting_evidence + h.contradicting_evidence})
        valid = self.client.ro_query(
            "MATCH (:Incident {id: $inc})-[:HAS_OBSERVATION]->(o:Observation) WHERE o.id IN $ids "
            "RETURN count(DISTINCT o) AS n", {"inc": r.incident_id, "ids": cited})[0]["n"] if cited else 0
        rec = [m for m in r.candidate_mitigations if m.verdict == "recommended" and m.action.type != "gather_more_evidence"]
        action, outcome = None, None
        if rec and simulate:
            action = rec[0].action
            outcome = self.sim.simulate(r.incident_id, action, approved=True).result
        ref = self._reference_affected(truth_root)
        pred_aff = set(r.affected_services.get("potential") or []) if r.mode != "A_incident_only" else \
            set(r.affected_services.get("observed") or []) - ({pred} if pred else set())
        bp, br = prf(pred_aff, ref) if pred else (0.0, 0.0)
        return {
            "incident_id": r.incident_id, "mode": r.mode, "truth_root": truth_root, "truth_fault": truth_fault,
            "predicted": pred, "ranked": ranked[:5], "conclusion": r.conclusion,
            "top1": pred == truth_root, "top3": truth_root in ranked[:3], "avg5": avg_at_k(ranked, truth_root),
            "fault_class_pred": r.suspected_fault_class,
            "fault_class_ok": r.suspected_fault_class == FAULT_CLASS.get(truth_fault),
            "evidence_cited": len(cited), "evidence_valid": valid,
            "action": action.model_dump() if action else None, "action_outcome": outcome,
            "blast_precision": round(bp, 3), "blast_recall": round(br, 3),
            "memories_applicable": sum(m.verdict == "applicable" for m in r.memories_considered),
            "memories_rejected": sum(m.verdict == "rejected" for m in r.memories_considered),
            "latency_ms": r.elapsed_ms,
        }

    def leakage_check(self, r: InvestigationReport) -> list[str]:
        blob = r.model_dump_json()
        issues = []
        case = self.case_of.get(r.incident_id)
        if case and case in blob:
            issues.append(f"case name present in report of {r.incident_id}")
        for k in ('"root_cause_service"', '"fault":', '"repetition"', '"split"'):
            if k in blob:
                issues.append(f"label key {k} present in report of {r.incident_id}")
        return issues

    # -- phases -------------------------------------------------------------------------------
    def history_phase(self, history: list[str]) -> list[dict]:
        log = []
        seen: list[str] = []
        for iid in history:
            r = self.inv.investigate(iid, "C_graph_memory", memory_sources=seen or ["__none__"])
            lab = self.labels[iid]
            rec = [m for m in r.candidate_mitigations if m.verdict == "recommended" and m.action.type != "gather_more_evidence"]
            attempts = []
            for m in rec[:2]:
                res = execute_simulated_action(self.tools, self.sim, iid, m.action, approved=True,
                                               idempotency_key="eval-history")
                attempts.append({"action": m.action.model_dump(), "result": res["outcome"]["result"]})
                if res["outcome"]["result"] == "resolved":
                    break
            log.append({"incident_id": iid, "predicted": r.suspected_root_cause, "truth_root": lab["root_cause_service"],
                        "attempts": attempts})
            seen.append(iid)
        return log

    def heldout_phase(self, heldout: list[str], history: list[str]) -> tuple[list[dict], list[str]]:
        rows, leaks = [], []
        for iid in heldout:
            lab = self.labels[iid]
            for mode in MODES:
                r = self.inv.investigate(iid, mode, memory_sources=history, related_allowed=history)
                leaks += self.leakage_check(r)
                rows.append(self.score(r, lab["root_cause_service"], lab["fault"]))
            loso = [h for h in history if self.labels[h]["root_cause_service"] != lab["root_cause_service"]]
            r = self.inv.investigate(iid, "C_graph_memory", memory_sources=loso, related_allowed=history)
            row = self.score(r, lab["root_cause_service"], lab["fault"])
            row["mode"] = "C_loso_control"
            rows.append(row)
        return rows, leaks

    def synthetic_phase(self) -> list[dict]:
        ids = self._detected(list(self.syn_truth))
        rows = []
        seen: list[str] = []
        for iid in ids:
            t = self.syn_truth[iid]
            for mode in MODES:
                r = self.inv.investigate(iid, mode, memory_sources=seen or ["__none__"])
                rows.append(self.score(r, t["root_cause_service"], t["fault"]))
            # Scripted operator step for memory Test C: a failed scale_out on the first checkout incident.
            from app.schemas.models import ActionSpec
            if iid == "SYN-checkout-socket-1":
                execute_simulated_action(self.tools, self.sim, iid, ActionSpec(type="scale_out", target="checkoutservice"),
                                         idempotency_key="eval-operator")
            else:
                r = self.inv.investigate(iid, "C_graph_memory", memory_sources=seen or ["__none__"])
                rec = [m for m in r.candidate_mitigations if m.verdict == "recommended" and m.action.type != "gather_more_evidence"]
                if rec:
                    execute_simulated_action(self.tools, self.sim, iid, rec[0].action, approved=True,
                                             idempotency_key="eval-synthetic")
            seen.append(iid)
        return rows


def summarize(rows: list[dict]) -> dict:
    out = {}
    for mode in sorted({r["mode"] for r in rows}):
        rs = [r for r in rows if r["mode"] == mode]
        n = len(rs)
        acted = [r for r in rs if r["action_outcome"]]
        cited = sum(r["evidence_cited"] for r in rs)
        out[mode] = {
            "n": n,
            "top1": round(sum(r["top1"] for r in rs) / n, 3),
            "top3": round(sum(r["top3"] for r in rs) / n, 3),
            "avg5": round(sum(r["avg5"] for r in rs) / n, 3),
            "abstained": sum(r["conclusion"] == "inconclusive" for r in rs),
            "fault_class_acc": round(sum(r["fault_class_ok"] for r in rs) / n, 3),
            "actions_taken": len(acted),
            "mitigation_success_rate": round(sum(r["action_outcome"] == "resolved" for r in acted) / len(acted), 3) if acted else None,
            "inappropriate_action_rate": round(sum(r["action_outcome"] != "resolved" for r in acted) / len(acted), 3) if acted else None,
            "worsened": sum(r["action_outcome"] == "worsened" for r in acted),
            "evidence_validity": round(sum(r["evidence_valid"] for r in rs) / cited, 3) if cited else None,
            "blast_precision": round(statistics.mean(r["blast_precision"] for r in rs), 3),
            "blast_recall": round(statistics.mean(r["blast_recall"] for r in rs), 3),
            "mean_applicable_memories": round(statistics.mean(r["memories_applicable"] for r in rs), 2),
            "latency_ms_median": round(statistics.median(r["latency_ms"] for r in rs), 1),
            "latency_ms_p95": round(sorted(r["latency_ms"] for r in rs)[max(0, int(0.95 * n) - 1)], 1),
        }
    return out


def run(settings: Settings, out_dir: Path, graph_name: str = "faultline_eval") -> dict:
    t0 = time.perf_counter()
    ev = Evaluator(settings, graph_name)
    load = ev.reset_graph()
    by_split = {k: [i for i, s in ev.split.items() if s == k and i in ev.labels] for k in ("history", "validation", "test")}
    history = ev._detected(by_split["history"])
    validation = ev._detected(by_split["validation"])
    test = sorted(by_split["test"])
    # Memory is built from all incidents that precede the evaluated split (chronologically within the pool).
    hist_log = ev.history_phase(history + validation)
    val_rows, leaks_v = ev.heldout_phase(sorted(validation), history) if validation else ([], [])
    test_rows, leaks_t = ev.heldout_phase(test, history + validation) if test else ([], [])
    dev_rows = []
    for iid in history:  # development-set accuracy (weights were developed on this split)
        lab = ev.labels[iid]
        for mode in ("A_incident_only", "B_graph"):
            dev_rows.append(ev.score(ev.inv.investigate(iid, mode), lab["root_cause_service"], lab["fault"], simulate=False))
    syn_rows = ev.synthetic_phase()
    integ = check_integrity(ev.client)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "graph": graph_name,
        "protocol": "see app/evaluation/runner.py docstring and docs/evaluation.md",
        "dataset": {"rcaeval_history": len(history), "rcaeval_validation": len(validation), "rcaeval_test": len(test),
                    "synthetic": len(ev.syn_truth), "source": ev.manifest["source"]},
        "graph_load": {k: load[k] for k in ("rcaeval_incidents", "synthetic_incidents")},
        "test_summary": summarize(test_rows) if test_rows else {},
        "validation_summary": summarize(val_rows) if val_rows else {},
        "history_summary_development_set": summarize(dev_rows),
        "synthetic_summary": summarize(syn_rows),
        "memory_phase": {"incidents": len(hist_log),
                         "memories_written": sum(len(h["attempts"]) for h in hist_log),
                         "resolved": sum(any(a["result"] == "resolved" for a in h["attempts"]) for h in hist_log),
                         "log": hist_log},
        "leakage_issues": leaks_v + leaks_t,
        "integrity_ok": integ["ok"], "integrity_problems": integ["problems"],
        "rows_test": test_rows, "rows_validation": val_rows, "rows_synthetic": syn_rows,
        "elapsed_s": round(time.perf_counter() - t0, 1),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ablation_results.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    (out_dir / "ablation_report.md").write_text(render_markdown(result), encoding="utf-8")
    return result


def render_markdown(res: dict) -> str:
    cols = [("top1", "Top-1"), ("top3", "Top-3"), ("avg5", "Avg@5"), ("fault_class_acc", "Fault class"),
            ("abstained", "Abstained"), ("mitigation_success_rate", "Mitigation success"),
            ("inappropriate_action_rate", "Inappropriate action"), ("worsened", "Worsened"),
            ("evidence_validity", "Evidence valid"), ("blast_precision", "Blast P"), ("blast_recall", "Blast R"),
            ("mean_applicable_memories", "Applicable mem."), ("latency_ms_median", "Median ms")]

    def table(summary: dict) -> str:
        head = "| Mode | n | " + " | ".join(c[1] for c in cols) + " |\n|" + "---|" * (len(cols) + 2) + "\n"
        return head + "".join(
            f"| {m} | {v['n']} | " + " | ".join("—" if v[c] is None else str(v[c]) for c, _ in cols) + " |\n"
            for m, v in summary.items())

    return (
        f"# Ablation results (generated {res['generated_at']})\n\n"
        f"Measured by `python scripts/evaluate.py`. Machine-readable: `ablation_results.json`.\n\n"
        f"## Headline: RCAEval RE2-OB TEST split (repetition 3, n={res['dataset']['rcaeval_test']}, "
        f"untouched during development)\n\n"
        + (table(res["test_summary"]) if res["test_summary"] else "_not run (rep 3 not ingested)_\n") +
        "\nMemory for TEST comes from history + validation incidents only.\n"
        f"\n## RCAEval RE2-OB VALIDATION split (repetition 2, n={res['dataset']['rcaeval_validation']}) "
        f"— used for failure analysis, therefore optimistic\n\n"
        + (table(res["validation_summary"]) if res["validation_summary"] else "_not run_\n") +
        "\n## RCAEval RE2-OB history (repetition 1) — development set, weights were set on it\n\n"
        + table(res["history_summary_development_set"]) +
        f"\n## Synthetic scenarios (n={res['dataset']['synthetic']}, hand-designed, chronological memory)\n\n"
        + table(res["synthetic_summary"]) +
        f"\n- Memory phase: {res['memory_phase']['memories_written']} simulated actions recorded as memory over "
        f"{res['memory_phase']['incidents']} prior incidents ({res['memory_phase']['resolved']} resolved).\n"
        f"- Leakage issues detected: {len(res['leakage_issues'])}. Graph integrity ok: {res['integrity_ok']}.\n"
        f"- Mitigation outcomes come from the deterministic simulator (see docs/architecture.md), not real systems.\n"
        f"- Blast-radius reference = architecture dependents of the true root (derived, not observed).\n"
    )
