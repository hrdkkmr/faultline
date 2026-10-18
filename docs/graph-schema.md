# Graph schema and Cypher

FalkorDB graph `faultline` (application). Evaluation runs use a separate graph, `faultline_eval`, and tests use
`faultline_test_<random>` graphs. All of them run in the same FalkorDB instance.

Counts after `python scripts/ingest.py --mode full --reps 1 2 3 --load-graph`: 12 Service, 97 Incident (90 RCAEval +
7 synthetic), 10,494 Observation, 110 Signal, 2 Deployment. These are before any investigation, action or memory.

## Node labels

| Label | Unique key | Key properties | Source (`source` property) |
|---|---|---|---|
| `System` | `id` | `name`, `ref` | architecture |
| `Service` | `name` | `kind` (service/datastore/entrypoint), `language`, `otel_counterpart` | architecture |
| `Incident` | `id` (`INC-<sha1>` or `SYN-…`) | `detected_at`, `detected_at_iso`, `window_start/end`, `has_metrics/logs/traces`, `title`, `status`, `provenance` | rcaeval / synthetic |
| `Observation` | `id` = `<incident>:<kind>:<service>:<signal>` | `kind` (metric/log/trace/call), `signal`, `score`, `direction`, `anomalous`, `baseline`, `observed`, `onset_s`, `raw_ref`, `samples`, `caller` | rcaeval / trace / synthetic |
| `Signal` | `key` = `service\|signal\|direction` | `service`, `signal`, `direction` | derived from anomalous observations |
| `Deployment` | `id` | `service`, `version`, `previous_version`, `at`, `change_type` | synthetic only (RCAEval has none) |
| `Investigation` | `id` | `mode`, `conclusion`, `top_service`, `fault_class`, `confidence`, `report` (JSON) | agent |
| `Hypothesis` | `id` | `service`, `fault_class`, `rank`, `score`, `status='hypothesis'` | agent |
| `Action` | `id` | `type`, `target`, `status` (`proposed` / `executed`), `risk`, `mode='simulated'` | agent / simulator |
| `Outcome` | `id` | `result` (resolved/not_resolved/worsened), `detail`, `side_effects`, `source` (simulator/operator) | simulator |
| `Memory` | `id` | `derived_from` (incident), `service`, `action_type`, `outcome`, `lesson`, `created_at`, `version`, `requires_deployment` | simulator outcome |

Unique constraints are created with `GRAPH.CONSTRAINT CREATE … UNIQUE NODE <label> PROPERTIES 1 <key>`, after an
exact-match index on the same property. FalkorDB rejects Cypher `CREATE CONSTRAINT`. The code is in
`backend/app/graph/schema.py`.

Ground-truth property names (`root_cause_service`, `fault`, `case`, …) are **forbidden**. The integrity check
fails if any of them appears in `db.propertyKeys()`.

## Relationships

| Relationship | Meaning | Provenance |
|---|---|---|
| `(System)-[:CONTAINS]->(Service)` | service belongs to the system | architecture |
| `(Service)-[:DEPENDS_ON]->(Service)` | caller is *configured* to call callee (`*_SERVICE_ADDR` env var in the Online Boutique manifests). Props: `evidence`, `ref` | **architecture-derived**, not observed |
| `(Service)-[:CALLS]->(Service)` | a parent span in the caller has a child span in the callee in at least one incident's traces. Props: `incidents` (list), `observed_in` | **trace-observed** (RCAEval traces) |
| `(Incident)-[:IN_SYSTEM]->(System)` | incident occurred in the system | ingestion |
| `(Incident)-[:HAS_OBSERVATION]->(Observation)` | observation was measured in the incident's window | rcaeval / synthetic |
| `(Observation)-[:OBSERVED_ON]->(Service)` | the observation is about that service | ingestion |
| `(Observation)-[:FROM_CALLER]->(Service)` | for `call` observations: the calling side | traces |
| `(Observation)-[:OF_SIGNAL]->(Signal)` | anomalous observation instantiates a failure-signature element | derived |
| `(Signal)-[:ON]->(Service)` | signature element is on that service | derived |
| `(Deployment)-[:CHANGED]->(Service)` | a release changed the service | synthetic |
| `(Investigation)-[:INVESTIGATED]->(Incident)` | investigation episode | agent |
| `(Investigation)-[:PROPOSED]->(Hypothesis)` | hypothesis produced by the investigation | agent |
| `(Hypothesis)-[:ABOUT]->(Service)` | hypothesized root-cause service | agent |
| `(Hypothesis)-[:SUPPORTED_BY]->(Observation)` | evidence for the hypothesis | agent, points at stored records |
| `(Hypothesis)-[:CONTRADICTED_BY]->(Observation)` | evidence against it (anomalous dependency, normal resource metrics) | agent |
| `(Hypothesis)-[:INFORMED_BY]->(Memory)` | memory that raised the hypothesis score | agent |
| `(Investigation)-[:RECOMMENDED]->(Action {status:'proposed'})` | ranked recommendation (`rank` prop) | agent |
| `(Action)-[:ADDRESSES]->(Hypothesis)`, `(Action)-[:TARGETS]->(Service)` | what the action is for and on | agent |
| `(Incident)-[:ATTEMPTED]->(Action {status:'executed'})` | action applied, always to the **simulator** | simulator |
| `(Action)-[:PRODUCED]->(Outcome)` | result of the attempt | simulator |
| `(Memory)-[:DERIVED_FROM]->(Outcome)` | episode memory built from an observed outcome | memory |
| `(Memory)-[:ABOUT]->(Service)` | memory target | memory |
| `(Memory)-[:APPLIES_UNDER]->(Signal)` | conditions that must hold for the lesson to apply | memory |
| `(Memory)-[:CONTRADICTS]->(Memory)` | same target + action with overlapping conditions, different outcome. Both are kept | memory |

Proposed schema elements that were **not** implemented, because there is no data with clear semantics:
`Alert`, `Trace`, `LogEvent`, `Runbook`, `PRECEDED`, `TRIGGERED`, `RESOLVED_BY`. Log lines and trace aggregates
are carried by `Observation` (`samples`, `raw_ref`).

## Cypher used by the agent

All queries are in `backend/app/graph/queries.py` and are parameterized. Variable-length bounds cannot be
parameters, so `{depth}` is substituted only with a validated int in `[1, FAULTLINE_MAX_DEPTH]` (`with_depth()`).

**Multi-hop dependency trace** (`trace_dependencies`)
```cypher
MATCH p = (s:Service {name: $service})-[:DEPENDS_ON|CALLS*1..{depth}]->(t:Service)
WHERE t <> s
RETURN t.name AS service, length(p) AS depth, [n IN nodes(p) | n.name] AS path,
       [r IN relationships(p) | type(r)] AS rel_types, [r IN relationships(p) | r.source] AS rel_sources
```

**Blast radius** (`calculate_blast_radius`): reverse architecture traversal plus observed impact in the incident.
```cypher
MATCH p = (u:Service)-[:DEPENDS_ON*1..{depth}]->(s:Service {name: $service}) WHERE u <> s
WITH u, min(length(p)) AS depth
OPTIONAL MATCH (i:Incident {id: $incident_id})-[:HAS_OBSERVATION]->(o:Observation {anomalous: true})-[:OBSERVED_ON]->(u)
RETURN u.name AS service, depth, collect(o.id) AS anomalous_observations
```

**Anomaly sub-graph reachability**: drives the explanation-coverage score.
```cypher
MATCH p = (a:Service)-[:DEPENDS_ON|CALLS*1..{depth}]->(b:Service)
WHERE a.name IN $services AND b.name IN $services AND a <> b
WITH a, b, p ORDER BY length(p)
WITH a, b, collect(p)[0] AS p
RETURN a.name AS caller, b.name AS callee, length(p) AS depth, [n IN nodes(p) | n.name] AS path
```

**Related incidents**: two hops through shared `Signal` nodes, ranked by Jaccard.
```cypher
MATCH (i:Incident {id: $incident_id})-[:HAS_OBSERVATION]->(:Observation)-[:OF_SIGNAL]->(g:Signal)
WITH i, collect(DISTINCT g) AS mine
UNWIND mine AS g
MATCH (g)<-[:OF_SIGNAL]-(:Observation)<-[:HAS_OBSERVATION]-(j:Incident) WHERE j <> i
...
RETURN j.id, shared, toFloat(size(shared)) / (n_mine + n_theirs - size(shared)) AS jaccard
```

**Applicable memories**. Candidates are memories whose `APPLIES_UNDER` conditions overlap the incident's
anomalous signals, **or** whose source incident looks similar. Applicability is then decided from
`required` vs `matched`:
```cypher
MATCH (i:Incident {id: $incident_id})
OPTIONAL MATCH (i)-[:HAS_OBSERVATION]->(:Observation)-[:OF_SIGNAL]->(g:Signal)
WITH collect(DISTINCT g.key) AS mine
MATCH (m:Memory)-[:APPLIES_UNDER]->(req:Signal) ...
RETURN m, required, [k IN required WHERE k IN mine] AS matched, source_similarity, contradicted_by
```

**Evidence paths for a stored hypothesis** (`HYPOTHESIS_EVIDENCE` + `SYMPTOM_PATHS`): reads `SUPPORTED_BY`,
`CONTRADICTED_BY` and `INFORMED_BY` edges, plus the shortest dependency path from every other anomalous service to the
hypothesized service.

Graph algorithms used: bounded variable-length path search (BFS-style shortest paths), reverse reachability
(blast radius), and set similarity over a bipartite incident–signal projection. FalkorDB's `algo.*` procedures
(e.g. `algo.pageRank`) are available, but the ranking does not use them. See `docs/architecture.md` for the
scoring formula.

## Example queries (FalkorDB Browser at http://localhost:3000)

```cypher
// Which services did traces observe calling each other, and are those calls in the architecture?
MATCH (a:Service)-[c:CALLS]->(b:Service)
RETURN a.name, b.name, c.observed_in, exists((a)-[:DEPENDS_ON]->(b)) AS in_architecture

// Every recorded outcome for an action on redis, with the conditions it was learned under
MATCH (m:Memory {service:'redis'})-[:APPLIES_UNDER]->(g:Signal)
RETURN m.action_type, m.outcome, m.derived_from, collect(g.key)

// Why was a hypothesis proposed?
MATCH (h:Hypothesis)-[:SUPPORTED_BY]->(o:Observation)-[:OBSERVED_ON]->(s)
RETURN h.id, h.service, o.signal, o.score, s.name ORDER BY h.id
```
