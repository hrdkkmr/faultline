"""Catalog of remediation actions Faultline may recommend. Actions are NEVER executed against real
systems; they can only be applied to the simulator.

`supporting_signals`: (signal, direction) pairs that must be anomalous on the action target for the
action's precondition to hold. Empty set = no signal precondition (e.g. rollback, which instead
requires a recent Deployment of the target).
"""

from __future__ import annotations

from dataclasses import dataclass, field

RESOURCE_SIGNALS = {"cpu", "mem", "diskio", "socket"}
LATENCY_SIGNALS = {"latency-50", "latency-90", "span_latency_p90", "call_latency_p90"}
ERROR_SIGNALS = {"error", "log_errors", "span_errors"}


@dataclass(frozen=True)
class ActionDef:
    type: str
    description: str
    risk: str  # none | low | medium | high
    requires_approval: bool
    supporting_signals: frozenset = field(default_factory=frozenset)
    requires_deployment: bool = False
    addresses: tuple[str, ...] = ()  # fault classes this action is designed for


ACTIONS: dict[str, ActionDef] = {
    "scale_out": ActionDef(
        "scale_out", "Add replicas to the target service", "low", False,
        frozenset({("cpu", "up"), ("workload", "up")}), addresses=("cpu",)),
    "increase_memory_limit": ActionDef(
        "increase_memory_limit", "Raise the target's memory limit and roll its pods", "low", False,
        frozenset({("mem", "up")}), addresses=("memory",)),
    "restart_service": ActionDef(
        "restart_service", "Restart the target's pods in place (same node)", "medium", True,
        frozenset({("mem", "up"), ("socket", "up")}), addresses=("memory", "socket")),
    "reschedule_pod": ActionDef(
        "reschedule_pod", "Evict the target's pods so they are rescheduled onto a different node", "high", True,
        frozenset({("diskio", "up"), ("latency-50", "up"), ("latency-90", "up"), ("span_latency_p90", "up"),
                   ("socket", "up"), ("mem", "up")}),
        addresses=("disk", "network", "memory", "socket")),
    "rollback_deployment": ActionDef(
        "rollback_deployment", "Roll the target back to its previous version", "medium", True,
        frozenset(), requires_deployment=True, addresses=("deployment_regression",)),
    "gather_more_evidence": ActionDef(
        "gather_more_evidence", "Collect more telemetry before acting (read-only)", "none", False),
}

RISK_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
