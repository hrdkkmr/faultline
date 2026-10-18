# Evaluation

Run: `python scripts/evaluate.py` (about 40 s; uses a fresh `faultline_eval` graph). It writes
`data/eval/results/ablation_results.json` and `ablation_report.md`. Two consecutive runs on 2026-10-16 produced
identical metrics.

## Approaches compared (same cases, same features)

| Mode | What it uses |
|---|---|
| **A_incident_only** | The incident's own observations only; score = local evidence strength. No dependency graph, no history. Action preconditions are checked only against the target's own signals. This is a fair magnitude-based baseline in the spirit of metric-only RCA (similar to BARO's ranking by anomaly magnitude), not a deliberately weakened one. |
| **B_graph** | A + dependency reachability (DEPENDS_ON/CALLS) for explanation coverage, deployments, blast radius, dependency-aware action checks |
| **C_graph_memory** | B + persistent memory retrieved from earlier incidents' recorded outcomes |
| **C_loso_control** | C, but memory restricted to earlier incidents with a *different* root-cause service. Measures harm from non-matching memories. The restriction uses labels on the evaluation side only |

## Protocol

1. Fresh graph: 90 RCAEval incidents + 7 synthetic scenarios.
2. Memory phase over reps 1+2 (60 incidents, chronological). For each: C-mode investigation using only memories from
   earlier incidents. The top recommendation is applied to the simulator; if it fails, the next one is tried once.
   Outcomes become memories (86 attempts, 55/60 incidents resolved).
3. Validation (rep 2) is scored with memory from rep 1; **test (rep 3)** with memory from reps 1+2. No memory writes
   happen during scoring.
4. Ground truth is loaded after each prediction. Each report is scanned for case names and label keys
   (0 issues).

## Metrics

Top-k: true root service among the first k hypotheses. Avg@5: RCAEval's mean of Top-1..Top-5. Fault class: inferred
class vs fault (delay and loss → network). Mitigation success: the top recommended action, applied to the simulator,
resolves the incident. Inappropriate action = 1 − success, among cases where an action was recommended.
Worsened: simulator side effect on a healthy request-path service. Evidence validity: share of cited observation
IDs that exist and belong to the incident. Blast P/R: predicted potential impact vs the architecture dependents of
the true root (a derived reference, not observed). For mode A, the prediction is the other anomalous services.

## Results (measured)

### Headline: TEST split, RCAEval RE2-OB repetition 3, n = 30 (untouched during development)

| Mode | Top-1 | Top-3 | Avg@5 | Fault class | Mitigation success | Worsened | Evidence valid | Blast P | Blast R | Median ms |
|---|---|---|---|---|---|---|---|---|---|---|
| A_incident_only | 0.933 | 1.0 | 0.973 | 0.733 | 0.667 | 0 | 1.0 | 0.531 | 0.528 | 34 |
| B_graph | 0.967 | 1.0 | 0.993 | 0.733 | 0.700 | 1 | 1.0 | 1.0 | 0.989 | 90 |
| C_graph_memory | 0.967 | 1.0 | 0.993 | 0.733 | **0.767** | 1 | 1.0 | 1.0 | 0.989 | 111 |
| C_loso_control | 0.867 | 0.967 | 0.960 | 0.700 | 0.483 | 2 | 1.0 | 1.0 | 0.944 | 110 |

### Validation split (rep 2): used for failure analysis, therefore optimistic

| Mode | Top-1 | Avg@5 | Mitigation success | Worsened | Blast P | Blast R |
|---|---|---|---|---|---|---|
| A | 0.900 | 0.967 | 0.667 | 2 | 0.424 | 0.453 |
| B | 1.000 | 1.000 | 0.700 | 0 | 1.0 | 1.0 |
| C | 0.967 | 0.993 | 0.833 | 1 | 1.0 | 0.989 |
| C_loso | 0.867 | 0.960 | 0.586 | 1 | 1.0 | 0.944 |

History (rep 1, development set): A Top-1 0.90, B 1.00. Synthetic (7 hand-designed cases): A/B/C all Top-1 1.0;
mitigation success A 0.857, B and C 1.0.

### What the measurements show

- **Graph vs no graph (B vs A):** blast-radius estimation improves sharply (P 0.53→1.0, R 0.53→0.99 on test). Top-1
  improves 0.933→0.967 on test, a difference of **one case in 30**. The graph's localization advantage on this
  benchmark is small because magnitude alone already localizes most RE2-OB faults. Where the graph helps is the
  propagation cases A gets wrong (e.g. productcatalog delay, where recommendationservice shows equally extreme
  latency).
- **Memory (C vs B):** mitigation success 0.70→0.77 on test (two more cases resolved); Top-1 unchanged. Memory mainly
  helps **choose the right action** for a well-localized cause.
- **Misleading memory (C_loso):** memory from *other* services' incidents hurts both localization (0.967→0.867) and
  mitigation (0.70→0.48). Condition-based matching is not enough protection when only cross-service memories exist.
  This is a measured limitation.
- n = 30 per split. Differences of one to three cases are not statistically established. No significance test was run.

### Development history (honest record)

- **v1** (archived at `data/eval/results/archive/`) used rep 2 as held-out. Results: A/B/C Top-1 0.90/0.90/0.90; C
  produced *worse* actions on cpu faults.
- Failure analysis on rep 2 found two mechanism issues: (a) memory effect summed over all matching memories, so a
  frequently tried action outvoted a more relevant one; (b) caller fan-out credit went to hub services for callees
  that had their own anomalous dependency. Both were fixed (`DECISIONS.md` D12). Rep 2 was then relabeled validation,
  and **rep 3 was downloaded afterwards** as the test split. The configuration was frozen (D13) before the single
  test evaluation reported above.

## Excluded and ambiguous

- No RCAEval cases were excluded (90/90 loaded).
- Fault class merges delay and loss into "network". `diskio` exists only for 3 of the 5 root services, so disk faults on
  checkout, currency and productcatalog cannot be identified from diskio.
- Mitigation metrics depend on the stylized simulator (`docs/architecture.md`). They measure consistency between the
  inferred cause/class and that model, not real-world repair efficacy.
