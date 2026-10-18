import { Database, FlaskConical, Globe, Info, Printer, Server, ShieldAlert, TriangleAlert } from "lucide-react";
import { ReactNode, useEffect, useMemo } from "react";
import { api, IncidentRow } from "../../api";
import { markGuideSeen } from "../../components/GuideHint";
import { href, IncidentTab } from "../../lib/router";
import { useAsync } from "../../lib/useAsync";
import Flyer from "./Flyer";
import { SECTIONS, WORKFLOW } from "./content";
import { SHOTS, ShotId } from "./shots";

/** Picks a real incident for deep links: the last one viewed, else an investigated scenario, else the first. */
function pickIncident(rows: IncidentRow[] | null, last: string | null) {
  if (!rows?.length) return null;
  if (last && rows.some((r) => r.id === last)) return last;
  return (rows.find((r) => r.source === "synthetic" && r.investigations > 0) ?? rows[0]).id;
}

export default function GuidePage({ section, lastIncident }: { section: string | null; lastIncident: string | null }) {
  const list = useAsync(() => api.incidents(), []);
  const demo = useMemo(() => pickIncident(list.data, lastIncident), [list.data, lastIncident]);
  const inc = (tab: IncidentTab = "graph") => (demo ? href({ page: "incidents", incident: demo, tab }) : href({ page: "incidents" }));

  useEffect(() => { markGuideSeen(); }, []);
  useEffect(() => {
    if (section && section !== "print") document.getElementById(`g-${section}`)?.scrollIntoView({ block: "start" });
    else document.querySelector(".page")?.scrollTo({ top: 0 });
  }, [section]);

  if (section === "print") return <Flyer />;

  return (
    <div className="guide">
      <nav className="guide-toc" aria-label="Guide sections">
        {SECTIONS.map((s) => (
          <a key={s.id} href={href({ page: "guide", section: s.id })} className={section === s.id ? "active" : ""}>
            <span className="toc-letter">{s.letter}</span>{s.title}
          </a>
        ))}
        <hr />
        <a href={href({ page: "guide", section: "print" })}><span className="toc-letter"><Printer size={11} /></span>Printable one-pager</a>
      </nav>

      <div className="guide-body">
        <header className="guide-hero">
          <h1>How to use Faultline</h1>
          <p>
            Faultline helps you work out why a microservice system is failing. It overlays an incident's anomalies on the
            service dependency graph stored in FalkorDB, ranks root-cause hypotheses with traceable evidence, and tests
            candidate repairs in a simulator.
          </p>
          <ol className="flow" aria-label="Investigation workflow">
            {WORKFLOW.map((w) => (
              <li key={w.n}>
                <a href={href({ page: "guide", section: w.s })}>
                  <span className="flow-n">{w.n}</span>
                  <span className="flow-t">{w.t}</span>
                  <span className="flow-d">{w.d}</span>
                </a>
              </li>
            ))}
          </ol>
          <div className="guide-hero-actions">
            <a className="btn-link" href={inc()}>Open an incident</a>
            <a className="btn-link ghost" href={href({ page: "guide", section: "print" })}><Printer size={14} /> Printable one-pager</a>
          </div>
        </header>

        <Sec id="start" shot="overview" intro="Everything starts from the incident list. The selected incident stays in the URL, so links and the browser's Back button work.">
          <Steps marked>
            <li><span><b>Incident list.</b> Search by ID, title or service. Filter by source (<i>Scenario</i>: hand-written synthetic case, <i>Benchmark</i>: RCAEval failure case) and by status.</span></li>
            <li><span><b>Status</b> is Open, Investigated, Resolved or Mitigation failed. It changes when you investigate or simulate an action here, not from a live production system.</span></li>
            <li><span><b>FalkorDB indicator.</b> Green means the graph answered a live query; hover it for the graph name, node count and latency. Red means it is unavailable and investigations will fail.</span></li>
            <li><span><b>Navigation rail.</b> Incidents, Memory &amp; Timeline, Evaluation, and this guide (the <b>?</b> at the bottom).</span></li>
          </Steps>
          <Links><a className="btn-link ghost" href={href({ page: "incidents" })}>Go to Incidents</a></Links>
        </Sec>

        <Sec id="investigate" shot="investigate" intro="The four tiles under the incident title summarise the incident and hold the investigation controls.">
          <Steps marked>
            <li><span><b>Summary tiles</b> show anomalous services, the blast radius and the root cause candidate. The last two stay empty (—) until an investigation has run.</span></li>
            <li><span><b>Choose a mode.</b> <i>Graph + Memory</i> uses dependency traversal and stored repair outcomes; <i>Graph only</i> ignores memory; <i>Incident only (baseline)</i> ranks services on their own anomalies without the graph.</span></li>
            <li><span><b>Press Investigate.</b> The button shows <i>Investigating</i> while the backend runs its graph queries. When it finishes, the tile shows the mode and run time. Every run is stored; switch between runs with the run dropdown.</span></li>
            <li><span><b>Read the result.</b> The candidate tile is always marked <i>unverified</i>. <i>Score share</i> is the top hypothesis's share of the ranking score, not a probability. <i>Inconclusive</i> means the evidence was too weak to rank a cause.</span></li>
          </Steps>
          <Links><a className="btn-link ghost" href={inc()}>Try it on an incident</a></Links>
        </Sec>

        <Sec id="graph" shot="graph" intro="The Architecture & Blast Radius tab is the main workspace. Every node and edge comes from the graph database; nothing is drawn by hand." wide={<>
          <h4>Reading the graph</h4>
          <div className="legend-grid">
            <Legend s={<span className="swatch-node"><Server size={12} /></span>}><b>Service</b>: no anomaly recorded in this incident</Legend>
            <Legend s={<span className="swatch-node anom"><Server size={12} /></span>}><b>Anomalous</b>: has at least one anomalous signal</Legend>
            <Legend s={<span className="swatch-node cand"><Database size={12} /></span>}><b>Root cause candidate</b>: dashed because it is unverified</Legend>
            <Legend s={<span className="swatch-node impact"><Server size={12} /></span>}><b>Potential impact</b>: upstream of the candidate</Legend>
            <Legend s={<span className="swatch-node sel"><Server size={12} /></span>}><b>Selected</b>: details open in the drawer</Legend>
            <Legend s={<span className="swatch-node"><Globe size={12} /></span>}>Icons: <b>globe</b> entrypoint, <b>server</b> service, <b>database</b> datastore</Legend>
            <Legend s={<span className="swatch-edge" />}><b>Depends on</b>: from the architecture manifests</Legend>
            <Legend s={<span className="swatch-edge trace" />}><b>Trace call</b>: observed in benchmark traces</Legend>
            <Legend s={<span className="swatch-edge path" />}><b>Impact path</b>: symptom → candidate chain</Legend>
          </div>
        </>}>
          <Steps marked>
            <li><span><b>Find service.</b> Type part of a name and press Enter to jump to it.</span></li>
            <li><span><b>Click a service</b> to open its drawer: observed signals with baseline → observed values, log samples when available, what it depends on, what calls it, and what would be affected if it failed.</span></li>
            <li><span><b>Controls</b> (bottom right): zoom in, zoom out, fit to view, reset layout. You can also scroll to zoom, drag the background to pan, and drag nodes.</span></li>
            <li><span><b>Toggles</b> above the graph: <i>Impact paths</i> highlights dependency chains from symptoms to the candidate, <i>Focus impacted</i> dims unaffected services, <i>Trace calls</i> shows calls seen in traces.</span></li>
          </Steps>
          <Links><a className="btn-link ghost" href={inc("graph")}>Open the graph</a></Links>
        </Sec>

        <Sec id="evidence" shot="evidence" intro="The Root Cause & Evidence tab shows why a service is suspected, and what argues against it." wide={<>
          <Callout icon={<Info size={15} />}>A candidate is a hypothesis. Faultline never labels a root cause as confirmed. <b>Data gaps</b> above the hypotheses list missing telemetry, and <b>Ranking rationale</b> and <b>Narrative</b> (collapsed) spell out how the ranking was reached.</Callout>
        </>}>
          <Steps marked>
            <li><span><b>Hypotheses</b> are ranked by score. Click one to inspect it; the first is the root cause candidate, the rest are alternatives.</span></li>
            <li><span><b>Score bars</b> split the ranking into local evidence (its own anomalies), graph coverage (how many other symptoms it explains through dependencies) and memory.</span></li>
            <li><span><b>Supporting and contradicting evidence</b> list the stored observations. Hover a row to see its observation ID in the graph. The score is a robust z-score against the pre-incident baseline.</span></li>
            <li><span><b>Evidence paths</b> show the dependency chains linking other anomalous services to the hypothesis, with their source (architecture or trace).</span></li>
          </Steps>
          <Links><a className="btn-link ghost" href={inc("evidence")}>Open evidence</a></Links>
        </Sec>

        <Sec id="mitigations" shot="mitigations" intro="The Mitigations tab lists candidate actions checked against the graph. Actions only ever run in the repair simulator." wide={<>
          <div className="compare">
            <div><h5>Proposed</h5>Suggested by the investigation; nothing has run.</div>
            <div><h5><FlaskConical size={13} /> Simulated</h5>Run in the repair simulator; the outcome is stored in memory.</div>
            <div><h5><ShieldAlert size={13} /> Verified</h5>Not available. Faultline never executes actions on real infrastructure, so no outcome is ever shown as verified.</div>
          </div>
        </>}>
          <Steps marked>
            <li><span><b>Each action</b> shows its verdict (recommended, needs more evidence, not recommended), risk, whether it needs approval, the net effect of past outcomes in memory, and any blockers.</span></li>
            <li><span><b>Preconditions and evidence</b> (expand) list what was checked and what blocks the action.</span></li>
            <li><span><b>Simulate.</b> Disruptive actions need <i>Approve</i> ticked first. The result says whether the simulated incident resolved and records the outcome as a memory.</span></li>
            <li><span><b>Status</b> reads <i>Proposed</i> until simulated, then <i>Simulated · outcome</i>. Not-recommended actions are collapsed at the bottom.</span></li>
          </Steps>
          <Links><a className="btn-link ghost" href={inc("mitigations")}>Open mitigations</a></Links>
        </Sec>

        <Sec id="memory" shot="history" intro="Simulated outcomes become memories, each tied to the signals that were present when it was learned." wide={<>
          <Callout icon={<TriangleAlert size={15} />}><b>Why a past fix can be rejected:</b> a memory applies only when the conditions it was learned under are present again. A restart that fixed a redis memory leak is rejected for an incident with the same storefront symptoms but no redis anomaly.</Callout>
          <p className="hint">The <b>Memory &amp; Timeline</b> page lists every memory (filter by outcome) and a timeline of investigated incidents with their actions.</p>
        </>}>
          <Steps marked>
            <li><span><b>Memories</b> in the Historical Context tab are marked applicable, partial or rejected for the current incident, with the reasons.</span></li>
            <li><span><b>Related incidents</b> share anomalous signals with this one; the percentage is their similarity. Click to open one.</span></li>
            <li><span><b>Actions on this incident</b> and <b>investigation runs</b> show what has already been tried. Open an older run to compare.</span></li>
          </Steps>
          <Links>
            <a className="btn-link ghost" href={inc("history")}>Open historical context</a>
            <a className="btn-link ghost" href={href({ page: "memory" })}>Go to Memory &amp; Timeline</a>
          </Links>
        </Sec>

        <Sec id="evaluation" shot="evaluation" intro="The Evaluation page reports how well the investigation modes perform, from the stored evaluation run." wide={<>
          <div className="compare">
            <div><h5>Measured</h5>Localization and blast-radius metrics on RCAEval benchmark telemetry.</div>
            <div><h5><FlaskConical size={13} /> Simulated</h5>Remediation rate and worsened counts come from the repair simulator.</div>
            <div><h5>Synthetic</h5>The Scenarios split uses hand-designed cases with deployments and prior repairs.</div>
          </div>
        </>}>
          <Steps marked>
            <li><span><b>Headline cards</b> show Graph + Memory on the held-out test split and its difference from the incident-only baseline.</span></li>
            <li><span><b>Results by mode</b>: switch splits (Test, Validation, Development, Scenarios). The <i>Samples</i> row is the number of cases. Hover a metric name for its definition; the best value in each row is highlighted.</span></li>
          </Steps>
          <p className="hint">Further down, <b>Per-case results</b> (collapsed) list every case with its ground truth. Labels appear only on this page, after predictions were made. <b>Run details</b> show the dataset revision and the leakage check.</p>
          <Links><a className="btn-link ghost" href={href({ page: "evaluation" })}>Go to Evaluation</a></Links>
        </Sec>

        <Sec id="troubleshooting" intro="Errors show a short summary; open Details for the technical message from the backend.">
          <div className="trouble">
            <div><h5>FalkorDB indicator is red</h5>The graph database is unreachable, and pages show “Graph database unavailable”. Start it with <code>docker compose up -d falkordb</code> and reload.</div>
            <div><h5>“Backend unreachable”</h5>The API is not running. Start it from <code>backend/</code> with <code>uvicorn app.main:app --port 8000</code>.</div>
            <div><h5>No incidents or an empty graph</h5>No data has been loaded. Run <code>python scripts/ingest.py --load-graph</code>.</div>
            <div><h5>Missing evidence</h5><i>Data gaps</i> list telemetry the incident lacks. “No dependency path” means the anomalies are not connected in the graph. <i>Inconclusive</i> means the evidence is too weak to rank a cause.</div>
            <div><h5>An investigation failed</h5>The error appears under the summary tiles. Open <i>Details</i> for the backend message, fix the cause, then press Investigate again.</div>
          </div>
        </Sec>
      </div>
    </div>
  );
}

function Sec({ id, shot, intro, children, wide }: {
  id: (typeof SECTIONS)[number]["id"]; shot?: ShotId; intro: string; children: ReactNode; wide?: ReactNode;
}) {
  const s = SECTIONS.find((x) => x.id === id)!;
  return (
    <section className="gsec" id={`g-${id}`} aria-labelledby={`g-${id}-h`}>
      <div className="gsec-head"><span className="gsec-letter" aria-hidden>{s.letter}</span><h2 id={`g-${id}-h`}>{s.title}</h2></div>
      <p className="gsec-intro">{intro}</p>
      <div className={`gsec-grid${shot ? "" : " solo"}`}>
        <div>{children}</div>
        {shot && <Shot id={shot} />}
      </div>
      {wide && <div className="gsec-wide">{wide}</div>}
    </section>
  );
}

function Shot({ id }: { id: ShotId }) {
  const s = SHOTS[id];
  const c = s.crop ?? { x: 0, y: 0, w: 100, h: 100 };
  return (
    <figure className="shot">
      <a className="shot-img" href={s.src} target="_blank" rel="noreferrer" title="Open full-size screenshot"
        style={{ aspectRatio: `${(c.w * s.w) / (c.h * s.h)}` }}>
        <img src={s.src} alt={s.alt} loading="lazy"
          style={{ width: `${(100 / c.w) * 100}%`, left: `${(-c.x / c.w) * 100}%`, top: `${(-c.y / c.h) * 100}%` }} />
        {s.markers.map((m) => {
          const left = ((m.x - c.x) / c.w) * 100;
          // Markers sit just left of their target; near the left edge they flip to the right so they are not clipped.
          return <span key={m.n} className={`marker${left < 5 ? " marker-right" : ""}`} style={{ left: `${left}%`, top: `${((m.y - c.y) / c.h) * 100}%` }} aria-hidden>{m.n}</span>;
        })}
      </a>
      <figcaption>{s.caption} · click to enlarge</figcaption>
    </figure>
  );
}

const Steps = ({ children, marked }: { children: ReactNode; marked?: boolean }) => <ol className={`steps${marked ? " marked" : ""}`}>{children}</ol>;
const Links = ({ children }: { children: ReactNode }) => <div className="gsec-links">{children}</div>;
const Callout = ({ icon, children }: { icon: ReactNode; children: ReactNode }) => <div className="callout">{icon}<span>{children}</span></div>;
const Legend = ({ s, children }: { s: ReactNode; children: ReactNode }) => <div className="legend-item">{s}<span>{children}</span></div>;
