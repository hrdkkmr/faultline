# Ablation results (generated 2026-10-16T13:50:00+00:00)

Measured by `python scripts/evaluate.py`. Machine-readable: `ablation_results.json`.

## RCAEval RE2-OB held-out (repetition 2, n=30 cases)

| Mode | n | Top-1 | Top-3 | Avg@5 | Fault class | Abstained | Mitigation success | Inappropriate action | Worsened | Evidence valid | Blast P | Blast R | Applicable mem. | Median ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_incident_only | 30 | 0.9 | 1.0 | 0.967 | 0.733 | 0 | 0.667 | 0.333 | 2 | 1.0 | 0.424 | 0.453 | 0 | 35.0 |
| B_graph | 30 | 0.9 | 1.0 | 0.98 | 0.767 | 0 | 0.667 | 0.333 | 3 | 1.0 | 1.0 | 0.928 | 0 | 89.2 |
| C_graph_memory | 30 | 0.9 | 1.0 | 0.973 | 0.733 | 0 | 0.733 | 0.267 | 1 | 1.0 | 1.0 | 0.961 | 1.73 | 100.9 |
| C_loso_control | 30 | 0.8 | 0.933 | 0.92 | 0.7 | 0 | 0.552 | 0.448 | 1 | 1.0 | 0.989 | 0.928 | 0.33 | 101.4 |

## RCAEval RE2-OB history (repetition 1) — development set, weights were set on it

| Mode | n | Top-1 | Top-3 | Avg@5 | Fault class | Abstained | Mitigation success | Inappropriate action | Worsened | Evidence valid | Blast P | Blast R | Applicable mem. | Median ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_incident_only | 30 | 0.9 | 1.0 | 0.973 | 0.633 | 0 | — | — | 0 | 1.0 | 0.377 | 0.458 | 0 | 30.5 |
| B_graph | 30 | 1.0 | 1.0 | 1.0 | 0.633 | 0 | — | — | 0 | 1.0 | 1.0 | 1.0 | 0 | 100.7 |

## Synthetic scenarios (n=7, hand-designed, chronological memory)

| Mode | n | Top-1 | Top-3 | Avg@5 | Fault class | Abstained | Mitigation success | Inappropriate action | Worsened | Evidence valid | Blast P | Blast R | Applicable mem. | Median ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_incident_only | 7 | 1.0 | 1.0 | 1.0 | 0.857 | 0 | 0.857 | 0.143 | 0 | 1.0 | 1.0 | 0.655 | 0 | 31.0 |
| B_graph | 7 | 1.0 | 1.0 | 1.0 | 1.0 | 0 | 1.0 | 0.0 | 0 | 1.0 | 1.0 | 1.0 | 0 | 113.5 |
| C_graph_memory | 7 | 1.0 | 1.0 | 1.0 | 1.0 | 0 | 1.0 | 0.0 | 0 | 1.0 | 1.0 | 1.0 | 0.14 | 113.7 |

- History phase: 40 simulated actions recorded as memory, 27/30 incidents resolved.
- Leakage issues detected: 0. Graph integrity ok: True.
- Mitigation outcomes come from the deterministic simulator (see docs/architecture.md), not real systems.
- Blast-radius reference = architecture dependents of the true root (derived, not observed).
