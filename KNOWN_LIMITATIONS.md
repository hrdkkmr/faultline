# Known Limitations

## Data
- RCAEval has no deployments, alerts, remediation actions or outcomes. Those parts of Faultline are exercised on 7
  clearly labeled synthetic scenarios and on simulated outcomes.
- RE2-OB traces cover only 7 of the 11 OB services (no spans for cart, ad, shipping, redis). Trace-observed `CALLS`
  edges are therefore partial (9 pairs); architecture `DEPENDS_ON` edges fill the gaps.
- RE2-OB root causes span only 5 services (checkout, currency, email, productcatalog, recommendation), and each
  (service, fault) pair repeats 3 times. Faultline ranks all 11 services, but repetition favours memory.
- `diskio` exists for only 3 of the 5 root services, so disk faults elsewhere are hard to classify. Fault-class
  accuracy is 0.70–0.73.
- Evaluation n = 30 per split. Differences of 1–3 cases are not statistically established.

## Method
- Ranking weights were set on rep 1, and two mechanism fixes were made after analysing rep 2 (`DECISIONS.md` D12).
  Only rep 3 is an unbiased test.
- **Misleading memory**: when only memories from other services exist (LOSO control), memory lowers Top-1
  (0.967→0.867) and mitigation success (0.70→0.48). Condition matching on `Signal` nodes does not fully prevent this.
- Temporal precedence (onset) is computed but not used for ranking; deployments are a weak +0.15 signal. Neither is
  treated as causation.
- The simulator is a stylized model (`docs/architecture.md`). Mitigation metrics measure consistency with that model,
  not real-world efficacy. No action is ever executed on a real system.
- Abstention threshold (local < 0.25) never triggered on RCAEval; it is exercised only by tests and weak synthetic input.

## Engineering
- **Persistence uses RDB snapshots, not AOF.** With AOF on, FalkorDB v4.22.0 segfaulted
  (`GraphContext_GetSchemaByID`) replaying a `GRAPH.EFFECT` entry after a constraint-violating write followed by graph
  deletion. That was reproduced in isolation (test-suite pattern). The `EFFECTS_THRESHOLD` workaround made replay take
  hours. Trade-off: up to 60 s of writes can be lost on a hard crash. Graceful `docker stop` saves a final snapshot,
  and restart-persistence was verified.
- Tests, the evaluation graph and the app graph share one FalkorDB instance (different graph names).
- The optional LLM narrator was tested only with a fake provider (timeout, invented-ID rejection, success). No API key
  was available, so a real Anthropic call was **not** exercised.
- No live public deployment; local setup only.
- No code LICENSE file was added. The owner must choose one before publishing. Data/reference licenses are in
  README.
- Frontend has no automated UI tests; it was verified manually in Chrome (investigate, evidence, approve/simulate,
  memory reuse, evaluation and memory views, graph controls, node drawer, 390 px and 1000 px widths, no console errors).
- Graph view: no minimap (12 services fit on screen; Cytoscape has no built-in minimap and a plugin was not worth a
  dependency). Node health is only "anomalous" or neutral; services without telemetry show as *Unknown* in the drawer,
  never as healthy. On phone widths the graph is small but zoomable.
- Guide screenshots are static captures (2026-10-18). They must be recaptured when the UI changes (docs/guide.md);
  nothing checks them automatically.
- Poppins is self-hosted; JetBrains Mono is not bundled, so IDs fall back to Cascadia Mono/Consolas.
- Severity is not shown anywhere: neither RCAEval nor the scenarios provide it, and the UI does not invent one.
