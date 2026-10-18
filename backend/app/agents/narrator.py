"""Narrators turn a finished, evidence-backed report into prose.

The deterministic narrator is the default. An optional LLM narrator (see llm.py) may rephrase, but
its output is accepted only if every evidence ID it cites exists in the report; otherwise the
deterministic text is used and the failure reason is recorded in `narrative_source`.
"""

from __future__ import annotations

from typing import Protocol

from app.schemas.models import InvestigationReport


class Narrator(Protocol):
    def narrate(self, report: InvestigationReport) -> tuple[str, str]: ...


def deterministic_narrative(r: InvestigationReport) -> str:
    if r.conclusion == "inconclusive":
        lines = [f"Investigation {r.investigation_id} of {r.incident_id} is INCONCLUSIVE."]
        lines += [f"- Missing: {m}" for m in r.missing_information]
        lines.append("Recommended next step: gather more evidence before acting.")
        return "\n".join(lines)
    h = r.hypotheses[0]
    lines = [
        f"Hypothesis (not verified): {h.service} is the most likely root cause "
        f"[{', '.join(h.supporting_evidence[:3])}], fault class '{h.fault_class}' ({h.fault_class_basis}).",
        f"Ranking score {h.score.total:.2f} (local {h.score.local_evidence:.2f}, coverage {h.score.coverage:.2f}, "
        f"memory {h.score.memory:.2f}); score share {r.confidence:.0%} among {len(r.hypotheses)} candidates.",
    ]
    for p in h.graph_paths[:4]:
        lines.append(f"- {p.service} is explained via {' -> '.join(p.path)} ({'/'.join(set(p.rel_types))}).")
    if h.contradicting_evidence:
        lines.append(f"Contradicting evidence: {', '.join(h.contradicting_evidence[:4])}.")
    if len(r.hypotheses) > 1:
        alt = r.hypotheses[1]
        lines.append(f"Main alternative: {alt.service} (score {alt.score.total:.2f}).")
    rec = [m for m in r.candidate_mitigations if m.verdict == "recommended"]
    if rec:
        m = rec[0]
        lines.append(f"Suggested mitigation: {m.action.type} on {m.action.target or '-'} (risk {m.risk}"
                     f"{', needs human approval' if m.requires_approval else ''}).")
    lines.append("Temporal ordering and correlation do not prove causation; verify before acting.")
    return "\n".join(lines)


class NullNarrator:
    def narrate(self, report: InvestigationReport) -> tuple[str, str]:
        return deterministic_narrative(report), "deterministic"
