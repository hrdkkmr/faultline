# Architecture

```mermaid
flowchart LR
  subgraph Sources
    R[RCAEval RE2-OB parquet<br/>HF @afeacb11]:::obs
    K[Online Boutique k8s manifests]:::arch
    S[Synthetic scenarios<br/>data/scenarios]:::syn
  end
  subgraph Backend[FastAPI backend]
    I[ingestion/<br/>features.py]
    L[graph/loader.py]
    T[agents/tools.py<br/>9 typed graph tools]
    V[agents/investigator.py<br/>+ ranking.py]
    N[agents/llm.py<br/>optional narrator]
    M[memory/service.py]
    X[simulation/simulator.py]
    E[evaluation/runner.py]
  end
  G[(FalkorDB v4.22.0<br/>Cypher)]
  GT[[data/eval/<br/>ground truth]]
  UI[React + Cytoscape UI]
  R --> I --> L --> G
  K --> L
  S --> L
  T <--> G
  V --> T
  V --> N
  M --> X
  M --> T
  X -. reads .-> GT
  E -. reads after prediction .-> GT
  E --> V
  UI <--> Backend
  classDef obs fill:#0c4a6e,color:#fff; classDef arch fill:#334155,color:#fff; classDef syn fill:#713f12,color:#fff;
```

Ground truth is read only by the simulator (to decide outcomes) and the evaluation runner (to score, after the
prediction). Agent code never imports it; `tests/test_stage10_adversarial.py` checks this statically.

## Components

| Module | Responsibility |
|---|---|
| `app/ingestion/rcaeval.py` | Case selection from `cases.parquet`, pinned HF revision, opaque IDs, manifest, labels file |
| `app/ingestion/features.py` | Raw telemetry → label-free Observations (robust z-scores, log rates, span latency, trace call edges) |
| `app/graph/loader.py` | Idempotent MERGE of architecture, incidents, observations, signals, calls, deployments |
| `app/graph/integrity.py` | Duplicate keys, orphans, missing links, forbidden label properties, architecture/trace disagreement |
| `app/agents/tools.py` | The 9 typed tools (below), all Cypher-backed |
| `app/agents/ranking.py` | Pure scoring functions (unit-tested without a DB) |
| `app/agents/investigator.py` | Orchestrates the tools, ranks hypotheses, abstains, selects mitigations, persists episodes |
| `app/agents/llm.py` | Optional Anthropic narrator; rejected unless every cited ID exists in the report |
| `app/simulation/` | Action catalog, deterministic simulator, scenario loader (visible vs hidden) |
| `app/memory/service.py` | Simulate → record Action/Outcome/Memory; list memories |
| `app/evaluation/runner.py` | A/B/C(+LOSO) ablation, metrics, leakage scan |
| `app/api/routes.py` | REST API used by the UI |

## Agent tools

| # | Tool | Graph operation |
|---|---|---|
| 1 | `trace_dependencies(service, max_depth, direction)` | bounded variable-length `DEPENDS_ON\|CALLS` paths |
| 2 | `calculate_blast_radius(service, incident_id)` | reverse `DEPENDS_ON*` traversal + incident anomalies |
| 3 | `inspect_incident(incident_id)` | incident + observations + linked services |
| 4 | `find_recent_changes(services, until_ts, window_s)` | `Deployment-[:CHANGED]->Service` in window; explicit "no change data" |
| 5 | `retrieve_related_incidents(incident_id)` | Jaccard over shared `Signal` nodes |
| 6 | `retrieve_evidence_paths(hypothesis_id)` | stored `SUPPORTED_BY` / `CONTRADICTED_BY` / `INFORMED_BY` + symptom paths |
| 7 | `retrieve_applicable_memories(incident_id)` | `Memory-[:APPLIES_UNDER]->Signal` matching, verdict + reasons |
| 8 | `evaluate_candidate_action(action, incident_id, memories)` | preconditions on target signals, deployments, anomalous dependencies, memory |
| 9 | `record_incident_outcome(incident_id, action, outcome)` | idempotent Action/Outcome/Memory write, `CONTRADICTS` linking |

Every tool validates its input (regex on IDs and service names, depth bounds), raises `NotFoundError` for unknown
entities, never invents a path, and raises `GraphUnavailableError` if FalkorDB is down. The API maps these to
404/422/503.

## Investigation workflow and scoring

1. `inspect_incident` → anomalous observations grouped by service = candidates.
2. (B, C) Cypher reachability among candidates (`ANOMALY_SUBGRAPH_PATHS`), recent changes, related incidents.
3. (C) applicable memories.
4. Scores (`app/agents/ranking.py`, frozen before the test split was evaluated):
   - `strength(o) = w(signal) · min(1, ln(1+z)/ln(1001))`. Weights: resource 1.0, latency/errors 0.8, span latency 0.7,
     call latency 0.6, log volume 0.4, workload 0.3. Resource metrics going **down** count at half weight, as
     symptoms of reduced load.
   - `local(s) = max strength + 0.05·min(4, #signals−1)`.
   - `explains(s,t)`: 1.0 if t transitively depends on s and has no local saturation; 0.5 if it does; 0.7 if s
     directly calls t, t shows only latency/error symptoms, and t has no anomalous dependency of its own (caller
     fan-out). Otherwise 0.
   - `coverage(s) = Σ local(t)·explains(s,t) / Σ local(t)` over the other anomalous services.
   - A = `local`; B = `0.5·local + 0.5·coverage (+0.15 if deployed ≤1h before)`; C = B `+ 0.3·max coverage of
     applicable resolved memories about s`.
5. Fault class from the top service's own signals (disk / cpu / memory / socket / network, or
   deployment_regression when a recent deployment coincides with no resource saturation).
6. Contradicting evidence: anomalous dependencies with their own resource anomaly ("may be a victim"), normal
   resource metrics on the hypothesized service.
7. **Abstain** (`inconclusive`, recommend `gather_more_evidence`) if no candidates or top `local < 0.25`.
8. Mitigations: every catalog action on the top hypothesis (and on the runner-up if within 85%) goes through
   `evaluate_candidate_action`. Ranking order: recommended first, then hypothesis rank, net memory effect
   (max success − max failure), whether the action addresses the inferred class, and lower risk.
9. Optional persistence: `Investigation`, `Hypothesis`, `SUPPORTED_BY`/`CONTRADICTED_BY`, proposed `Action` nodes.

The report is a hypothesis, never a verified cause. The narrative says so, and temporal precedence is never treated
as proof of causation.

## Memory design

- An episode is created only from an **outcome** (simulated or operator-recorded), never from a conversation.
- Conditions = the anomalous `Signal`s on the action target in the source incident (`APPLIES_UNDER`).
- Retrieval: candidates via condition overlap or source-incident similarity. Verdicts: `applicable` (all conditions
  present), `partial` (≥50%), `rejected` (otherwise, or target not anomalous, or a required deployment is missing).
  Conflicting outcomes are flagged.
- Use: a resolved memory adds to the hypothesis score; a failed one blocks the same action under matching conditions
  and never adds support.
- Update policy: append-only. Re-recording the same attempt (same idempotency key) is a no-op. A contradicting outcome
  adds a new Memory with `CONTRADICTS`.
- Persistence: FalkorDB RDB snapshots on a Docker volume (see `KNOWN_LIMITATIONS.md` for why AOF is disabled).

## Repair simulator

Actions are never executed against a real system. The outcome is decided only by hidden truth plus this fixed
model:

| Fault (truth) | Modeled cause | Effective actions on the true root |
|---|---|---|
| cpu | load above capacity | `scale_out` |
| mem | memory leak | `restart_service`, `increase_memory_limit`, `reschedule_pod` |
| socket | socket/connection leak | `restart_service`, `reschedule_pod` |
| disk | noisy-neighbour disk I/O on node | `reschedule_pod` |
| delay / loss | degraded node network path | `reschedule_pod` |
| deployment_regression (synthetic) | bad release | `rollback_deployment` |

Any action on another service does not resolve the incident. Disruptive actions (`restart_service`, `reschedule_pod`,
`rollback_deployment`) on a healthy request-path service are recorded as `worsened`. Disruptive actions require
`approved: true`; otherwise the API returns 403. This is a stylized model chosen for this project, not a property
of RCAEval.

## Architecture reference mapping (Online Boutique → OpenTelemetry Astronomy Shop)

| Online Boutique (RCAEval) | OTel demo | Note |
|---|---|---|
| frontend-external | frontend-proxy (Envoy) | entrypoint |
| frontend | frontend | |
| cartservice / redis | cart / valkey-cart | |
| productcatalogservice | product-catalog | OTel adds PostgreSQL |
| currencyservice, paymentservice, shippingservice, emailservice, checkoutservice, recommendationservice, adservice | currency, payment, shipping, email, checkout, recommendation, ad | |
| — | accounting, fraud-detection, kafka, flagd, quote, image-provider | not in Online Boutique; not modeled |

## Optional LLM narrator

`FAULTLINE_LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` enables it (`claude-opus-5-5`, low effort, server-side
refusal fallback). It receives only the finished report. Its output is discarded in favour of the deterministic
text if it times out, errors, cites an ID not in the report, cites nothing, or uses "confirmed/verified/proven".
Without a key, everything works deterministically.
