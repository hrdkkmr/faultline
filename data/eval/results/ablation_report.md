# Ablation results (generated 2026-10-16T15:19:01+00:00)

Measured by `python scripts/evaluate.py`. Machine-readable: `ablation_results.json`.

## Headline: RCAEval RE2-OB TEST split (repetition 3, n=30, untouched during development)

| Mode | n | Top-1 | Top-3 | Avg@5 | Fault class | Abstained | Mitigation success | Inappropriate action | Worsened | Evidence valid | Blast P | Blast R | Applicable mem. | Median ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_incident_only | 30 | 0.933 | 1.0 | 0.973 | 0.733 | 0 | 0.667 | 0.333 | 0 | 1.0 | 0.531 | 0.528 | 0 | 30.7 |
| B_graph | 30 | 0.967 | 1.0 | 0.993 | 0.733 | 0 | 0.7 | 0.3 | 1 | 1.0 | 1.0 | 0.989 | 0 | 76.9 |
| C_graph_memory | 30 | 0.967 | 1.0 | 0.993 | 0.733 | 0 | 0.767 | 0.233 | 1 | 1.0 | 1.0 | 0.989 | 0.43 | 92.5 |
| C_loso_control | 30 | 0.867 | 0.967 | 0.96 | 0.7 | 0 | 0.483 | 0.517 | 2 | 1.0 | 1.0 | 0.944 | 0 | 91.4 |

Memory for TEST comes from history + validation incidents only.

## RCAEval RE2-OB VALIDATION split (repetition 2, n=30) — used for failure analysis, therefore optimistic

| Mode | n | Top-1 | Top-3 | Avg@5 | Fault class | Abstained | Mitigation success | Inappropriate action | Worsened | Evidence valid | Blast P | Blast R | Applicable mem. | Median ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_incident_only | 30 | 0.9 | 1.0 | 0.967 | 0.733 | 0 | 0.667 | 0.333 | 2 | 1.0 | 0.424 | 0.453 | 0 | 31.3 |
| B_graph | 30 | 1.0 | 1.0 | 1.0 | 0.7 | 0 | 0.7 | 0.3 | 0 | 1.0 | 1.0 | 1.0 | 0 | 71.9 |
| C_graph_memory | 30 | 0.967 | 1.0 | 0.993 | 0.7 | 0 | 0.833 | 0.167 | 1 | 1.0 | 1.0 | 0.989 | 0.43 | 83.0 |
| C_loso_control | 30 | 0.867 | 1.0 | 0.96 | 0.733 | 0 | 0.586 | 0.414 | 1 | 1.0 | 1.0 | 0.944 | 0 | 82.8 |

## RCAEval RE2-OB history (repetition 1) — development set, weights were set on it

| Mode | n | Top-1 | Top-3 | Avg@5 | Fault class | Abstained | Mitigation success | Inappropriate action | Worsened | Evidence valid | Blast P | Blast R | Applicable mem. | Median ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_incident_only | 30 | 0.9 | 1.0 | 0.973 | 0.633 | 0 | — | — | 0 | 1.0 | 0.377 | 0.458 | 0 | 30.9 |
| B_graph | 30 | 1.0 | 1.0 | 1.0 | 0.633 | 0 | — | — | 0 | 1.0 | 1.0 | 1.0 | 0 | 85.6 |

## Synthetic scenarios (n=7, hand-designed, chronological memory)

| Mode | n | Top-1 | Top-3 | Avg@5 | Fault class | Abstained | Mitigation success | Inappropriate action | Worsened | Evidence valid | Blast P | Blast R | Applicable mem. | Median ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_incident_only | 7 | 1.0 | 1.0 | 1.0 | 0.857 | 0 | 0.857 | 0.143 | 0 | 1.0 | 1.0 | 0.655 | 0 | 29.5 |
| B_graph | 7 | 1.0 | 1.0 | 1.0 | 1.0 | 0 | 1.0 | 0.0 | 0 | 1.0 | 1.0 | 1.0 | 0 | 76.5 |
| C_graph_memory | 7 | 1.0 | 1.0 | 1.0 | 1.0 | 0 | 1.0 | 0.0 | 0 | 1.0 | 1.0 | 1.0 | 0.14 | 94.1 |

- Memory phase: 86 simulated actions recorded as memory over 60 prior incidents (55 resolved).
- Leakage issues detected: 0. Graph integrity ok: True.
- Mitigation outcomes come from the deterministic simulator (see docs/architecture.md), not real systems.
- Blast-radius reference = architecture dependents of the true root (derived, not observed).
