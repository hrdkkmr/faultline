# Five-minute demo script

Not recorded yet. This is the plan and the exact steps.

## Before recording

```bash
docker compose down -v && docker compose up -d falkordb          # empty graph: memory starts clean
python scripts/ingest.py --skip-features --load-graph              # 90 RCAEval + 7 synthetic incidents
cd backend && uvicorn app.main:app --port 8000                     # terminal 2
cd frontend && npm run dev                                         # terminal 3, open http://localhost:5173
```
Optional: open the FalkorDB Browser at http://localhost:3000 in a second tab.

## Script

| Time | Show | Say |
|---|---|---|
| 0:00 | Header health badge, legend | "Faultline investigates microservice failures by reasoning over a FalkorDB knowledge graph. Every element is labeled: observed, architecture-derived, trace-observed, hypothesis, simulated, memory." |
| 0:20 | Filter **rcaeval**, open an RCAEval incident, Investigate (mode C) | "This is a real RCAEval RE2-OB failure case. Its ID is opaque because the dataset folder name encodes the answer. The agent runs Cypher: multi-hop reachability among anomalous services, blast radius, memory retrieval, action checks." |
| 1:00 | Hypothesis panel → click #1, Evidence panel, amber paths on graph | "The top hypothesis cites stored observation IDs. Click one to see the raw record. Amber edges are the dependency paths that explain the other anomalous services. That is the graph's contribution: *coverage*." |
| 1:40 | Blast radius + mitigations | "Blast radius comes from reverse DEPENDS_ON traversal. Every mitigation is checked against preconditions in the graph; risky ones need approval and only run in a simulator." |
| 2:10 | Open **SYN-redis-mem-1**, Investigate, tick approve on `restart_service redis`, Simulate | "A labeled synthetic scenario. The simulator resolves it, and the outcome is stored as a Memory node with the conditions it was learned under." |
| 2:40 | Terminal: stop and restart the backend (`Ctrl+C`, rerun uvicorn). Open **SYN-redis-mem-2**, Investigate | "New session, same graph. The earlier repair is retrieved: applicable, 100% of its conditions present. It moves restart_service to the top." |
| 3:20 | Open **SYN-cart-deploy**, Investigate | "Same storefront symptoms, but redis is healthy and cart was just deployed. The redis memory is *rejected*, with the reason shown, and the agent recommends rollback instead." |
| 3:50 | **Evaluation** tab | "Measured on 30 untouched test cases: graph Top-1 0.97 vs 0.93 without it, blast-radius precision 1.0 vs 0.53, memory raises mitigation success from 0.70 to 0.77. And an honest negative: memories from other services hurt, see the LOSO row." |
| 4:30 | Terminal: `docker compose stop falkordb`, click Investigate | "Remove FalkorDB and the investigation fails with a 503. There is no fallback answer, because the reasoning lives in the graph." Restart with `docker compose start falkordb`. |
| 4:50 | — | "Tracks: Agents That Act on Connected Data (primary), Agent Memory (secondary)." |

## Backup (if the UI misbehaves)

`python scripts/e2e_check.py --phase 1`, restart backend + `docker compose restart falkordb`,
`python scripts/e2e_check.py --phase 2`, `docker compose stop falkordb`, `python scripts/e2e_check.py --phase down`.
