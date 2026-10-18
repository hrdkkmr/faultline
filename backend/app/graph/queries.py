"""Named Cypher queries used by the agent tools. Single source of truth (also cited in docs/graph-schema.md).

Rules:
- All values are passed as parameters ($name).
- Variable-length bounds cannot be parameters in Cypher, so `{depth}` is substituted only with a
  validated int (1..FAULTLINE_MAX_DEPTH) via `with_depth()`.
- Labels/relationship types are never taken from user input.
"""

from __future__ import annotations

SERVICE_EXISTS = "MATCH (s:Service {name: $service}) RETURN s.name AS name, s.kind AS kind LIMIT 1"

LIST_SERVICES = """
MATCH (s:Service)
OPTIONAL MATCH (s)-[d:DEPENDS_ON]->(t:Service)
RETURN s.name AS name, s.kind AS kind, s.language AS language, s.otel_counterpart AS otel,
       collect(t.name) AS depends_on
ORDER BY name
"""

# Downstream: what `service` depends on (callees), transitively.
TRACE_DOWNSTREAM = """
MATCH p = (s:Service {name: $service})-[:DEPENDS_ON|CALLS*1..{depth}]->(t:Service)
WHERE t <> s
RETURN t.name AS service, length(p) AS depth,
       [n IN nodes(p) | n.name] AS path,
       [r IN relationships(p) | type(r)] AS rel_types,
       [r IN relationships(p) | r.source] AS rel_sources
ORDER BY depth, service
"""

# Upstream: who depends on `service` (callers), transitively.
TRACE_UPSTREAM = """
MATCH p = (t:Service)-[:DEPENDS_ON|CALLS*1..{depth}]->(s:Service {name: $service})
WHERE t <> s
RETURN t.name AS service, length(p) AS depth,
       [n IN nodes(p) | n.name] AS path,
       [r IN relationships(p) | type(r)] AS rel_types,
       [r IN relationships(p) | r.source] AS rel_sources
ORDER BY depth, service
"""

# Blast radius: services that (transitively) depend on `service`, plus whether each shows an
# anomaly in the given incident.
BLAST_RADIUS = """
MATCH p = (u:Service)-[:DEPENDS_ON*1..{depth}]->(s:Service {name: $service})
WHERE u <> s
WITH u, min(length(p)) AS depth
OPTIONAL MATCH (i:Incident {id: $incident_id})-[:HAS_OBSERVATION]->(o:Observation {anomalous: true})
               -[:OBSERVED_ON]->(u)
RETURN u.name AS service, u.kind AS kind, depth, collect(o.id) AS anomalous_observations
ORDER BY depth, service
"""

INCIDENT = """
MATCH (i:Incident {id: $incident_id})
OPTIONAL MATCH (i)-[:IN_SYSTEM]->(sys:System)
RETURN i AS incident, sys.id AS system
"""

INCIDENT_OBSERVATIONS = """
MATCH (i:Incident {id: $incident_id})-[:HAS_OBSERVATION]->(o:Observation)
OPTIONAL MATCH (o)-[:OBSERVED_ON]->(s:Service)
WHERE $only_anomalous = false OR o.anomalous = true
WITH o, s
WHERE $only_anomalous = false OR o.anomalous = true
RETURN o AS observation, s.name AS linked_service
ORDER BY o.score DESC
"""

LIST_INCIDENTS = """
MATCH (i:Incident)
OPTIONAL MATCH (i)-[:HAS_OBSERVATION]->(o:Observation {anomalous: true})
WITH i, count(o) AS anomalous, collect(DISTINCT o.service)[0..6] AS services
OPTIONAL MATCH (inv:Investigation)-[:INVESTIGATED]->(i)
RETURN i.id AS id, i.title AS title, i.source AS source, i.status AS status,
       i.detected_at AS detected_at, i.detected_at_iso AS detected_at_iso, anomalous,
       services AS anomalous_services, count(inv) AS investigations
ORDER BY i.source DESC, i.detected_at
"""

RECENT_CHANGES = """
MATCH (d:Deployment)-[:CHANGED]->(s:Service)
WHERE s.name IN $services AND d.at >= $since AND d.at <= $until
RETURN d.id AS id, s.name AS service, d.version AS version, d.previous_version AS previous_version,
       d.at AS at, d.change_type AS change_type, d.description AS description, d.source AS source
ORDER BY d.at DESC
"""

COUNT_DEPLOYMENTS = "MATCH (d:Deployment) RETURN count(d) AS n"

# Incidents sharing anomalous Signal nodes with the given incident (2-hop through Signal).
RELATED_INCIDENTS = """
MATCH (i:Incident {id: $incident_id})-[:HAS_OBSERVATION]->(:Observation)-[:OF_SIGNAL]->(g:Signal)
WITH i, collect(DISTINCT g) AS mine
UNWIND mine AS g
MATCH (g)<-[:OF_SIGNAL]-(:Observation)<-[:HAS_OBSERVATION]-(j:Incident)
WHERE j <> i AND (size($allowed) = 0 OR j.id IN $allowed)
WITH j, mine, collect(DISTINCT g.key) AS shared
MATCH (j)-[:HAS_OBSERVATION]->(:Observation)-[:OF_SIGNAL]->(gj:Signal)
WITH j, size(mine) AS n_mine, shared, count(DISTINCT gj) AS n_theirs
RETURN j.id AS incident_id, j.title AS title, j.source AS source, shared,
       toFloat(size(shared)) / (n_mine + n_theirs - size(shared)) AS jaccard
ORDER BY jaccard DESC, incident_id
LIMIT $limit
"""

HYPOTHESIS_EVIDENCE = """
MATCH (h:Hypothesis {id: $hypothesis_id})-[:ABOUT]->(s:Service)
OPTIONAL MATCH (h)-[sb:SUPPORTED_BY]->(o:Observation)-[:OBSERVED_ON]->(os:Service)
WITH h, s, collect(CASE WHEN o IS NULL THEN NULL ELSE
     {observation: o.id, service: os.name, signal: o.signal, score: o.score, weight: sb.weight,
      kind: o.kind, source: o.source} END) AS support
OPTIONAL MATCH (h)-[:CONTRADICTED_BY]->(c:Observation)
WITH h, s, support, collect(CASE WHEN c IS NULL THEN NULL ELSE
     {observation: c.id, service: c.service, signal: c.signal, score: c.score} END) AS contra
OPTIONAL MATCH (h)-[im:INFORMED_BY]->(m:Memory)
RETURN h AS hypothesis, s.name AS service, support, contra,
       collect(CASE WHEN m IS NULL THEN NULL ELSE {memory: m.id, effect: im.effect} END) AS memories
"""

# Dependency paths from symptomatic services to the hypothesized root cause, in an incident.
SYMPTOM_PATHS = """
MATCH (i:Incident {id: $incident_id})-[:HAS_OBSERVATION]->(o:Observation {anomalous: true})-[:OBSERVED_ON]->(u:Service)
WHERE u.name <> $service
WITH DISTINCT u
MATCH p = (u)-[:DEPENDS_ON|CALLS*1..{depth}]->(s:Service {name: $service})
WITH u, p ORDER BY length(p)
WITH u, collect(p)[0] AS p
RETURN u.name AS from_service, length(p) AS depth, [n IN nodes(p) | n.name] AS path,
       [r IN relationships(p) | type(r)] AS rel_types, [r IN relationships(p) | r.source] AS rel_sources
ORDER BY depth, from_service
"""

# Candidate memories: those whose applicability conditions (Signal nodes) overlap this incident's
# anomalous signals, OR whose source incident looks similar (shares anomalous signals). Whether a
# candidate actually applies is decided afterwards from `required` vs `matched`.
APPLICABLE_MEMORIES = """
MATCH (i:Incident {id: $incident_id})
OPTIONAL MATCH (i)-[:HAS_OBSERVATION]->(:Observation)-[:OF_SIGNAL]->(g:Signal)
WITH collect(DISTINCT g.key) AS mine
MATCH (m:Memory)
WHERE (size($allowed_sources) = 0 OR m.derived_from IN $allowed_sources) AND m.derived_from <> $incident_id
MATCH (m)-[:APPLIES_UNDER]->(req:Signal)
WITH mine, m, collect(req.key) AS required
OPTIONAL MATCH (src:Incident {id: m.derived_from})-[:HAS_OBSERVATION]->(:Observation)-[:OF_SIGNAL]->(sg:Signal)
WITH mine, m, required, collect(DISTINCT sg.key) AS source_signals
WITH m, required, [k IN required WHERE k IN mine] AS matched,
     [k IN source_signals WHERE k IN mine] AS shared, size(source_signals) AS n_src, size(mine) AS n_mine
WHERE size(matched) > 0 OR size(shared) > 0
OPTIONAL MATCH (m)-[:CONTRADICTS]-(other:Memory)
RETURN m AS memory, required, matched, shared AS shared_with_source,
       CASE WHEN n_src + n_mine - size(shared) = 0 THEN 0.0
            ELSE toFloat(size(shared)) / (n_src + n_mine - size(shared)) END AS source_similarity,
       collect(DISTINCT other.id) AS contradicted_by
ORDER BY toFloat(size(matched)) / size(required) DESC, source_similarity DESC, m.created_at DESC
LIMIT $limit
"""

MEMORY_DETAIL = """
MATCH (m:Memory {id: $memory_id})
OPTIONAL MATCH (m)-[:DERIVED_FROM]->(out:Outcome)<-[:PRODUCED]-(a:Action)
OPTIONAL MATCH (m)-[:ABOUT]->(s:Service)
OPTIONAL MATCH (m)-[:APPLIES_UNDER]->(g:Signal)
RETURN m AS memory, out AS outcome, a AS action, s.name AS service, collect(g.key) AS conditions
"""

ANOMALOUS_SIGNALS_OF_INCIDENT = """
MATCH (i:Incident {id: $incident_id})-[:HAS_OBSERVATION]->(o:Observation)-[:OF_SIGNAL]->(g:Signal)
RETURN g.key AS key, o.id AS observation, o.score AS score
"""

SERVICE_ANOMALIES_IN_INCIDENT = """
MATCH (i:Incident {id: $incident_id})-[:HAS_OBSERVATION]->(o:Observation {anomalous: true})-[:OBSERVED_ON]->(s:Service {name: $service})
RETURN o.id AS id, o.kind AS kind, o.signal AS signal, o.score AS score, o.direction AS direction
ORDER BY o.score DESC
"""

# Anomalous direct dependencies (downstream) of a service in an incident: "is this service a victim?"
ANOMALOUS_DEPENDENCIES = """
MATCH (s:Service {name: $service})-[:DEPENDS_ON|CALLS]->(t:Service)
WITH DISTINCT t
MATCH (i:Incident {id: $incident_id})-[:HAS_OBSERVATION]->(o:Observation {anomalous: true})-[:OBSERVED_ON]->(t)
RETURN t.name AS service, max(o.score) AS max_score, collect(o.id)[0..5] AS observations
"""


# Reachability among a set of services (the incident's anomalous services): for every ordered pair
# (caller -> ... -> callee) the shortest dependency path. Drives explanation coverage in ranking.
ANOMALY_SUBGRAPH_PATHS = """
MATCH p = (a:Service)-[:DEPENDS_ON|CALLS*1..{depth}]->(b:Service)
WHERE a.name IN $services AND b.name IN $services AND a <> b
WITH a, b, p ORDER BY length(p)
WITH a, b, collect(p)[0] AS p
RETURN a.name AS caller, b.name AS callee, length(p) AS depth, [n IN nodes(p) | n.name] AS path,
       [r IN relationships(p) | type(r)] AS rel_types, [r IN relationships(p) | r.source] AS rel_sources
"""


def with_depth(query: str, depth: int, max_depth: int) -> str:
    if not isinstance(depth, int) or isinstance(depth, bool) or not 1 <= depth <= max_depth:
        raise ValueError(f"depth must be an int in [1, {max_depth}], got {depth!r}")
    return query.replace("{depth}", str(depth))
