import { ArrowLeft, Printer } from "lucide-react";
import { href } from "../../lib/router";
import { WORKFLOW } from "./content";

/** One-page, print-friendly summary of the guide. Printing uses the browser's own dialog (Save as PDF works there). */
export default function Flyer() {
  return (
    <div className="flyer-wrap">
      <div className="flyer-bar">
        <a className="btn-link ghost" href={href({ page: "guide" })}><ArrowLeft size={14} /> Back to guide</a>
        <button className="btn-primary" onClick={() => window.print()}><Printer size={14} /> Print</button>
        <span className="muted">A4, one page · choose “Save as PDF” in the print dialog for a file</span>
      </div>

      <article className="flyer" aria-label="Faultline one-page guide">
        <h1><span className="fly-mark" aria-hidden>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <path d="M3 8h8l2 3h8" /><path d="M3 16h6l2-3" /><path d="M15 16h6" />
          </svg></span>Faultline</h1>
        <p className="fly-lede">
          Graph-based incident investigation. Faultline overlays an incident's anomalies on the service dependency graph in
          FalkorDB, ranks root-cause hypotheses with traceable evidence, and tests repairs in a simulator, never on real systems.
        </p>

        <h2>The workflow</h2>
        <ol className="fly-flow">
          {WORKFLOW.map((w) => <li key={w.n}><b>{w.n}. {w.t}</b><span>{w.d}</span></li>)}
        </ol>

        <div className="fly-cols">
          <div>
            <h2>Graph → evidence → mitigation</h2>
            <svg className="fly-diagram" viewBox="0 0 400 200" role="img" aria-label="Illustration: symptoms in frontend, checkout and cart trace back along dependency edges to a redis root-cause candidate, which leads to a simulated restart">
              <defs>
                <marker id="fa" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="#c58a12" /></marker>
                <marker id="fg" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="#999" /></marker>
              </defs>
              <g fontFamily="Poppins, sans-serif" fontSize="11">
                <rect x="10" y="40" width="80" height="28" rx="8" fill="#fdecec" stroke="#d94545" strokeWidth="1.5" /><text x="50" y="58" textAnchor="middle">frontend</text>
                <rect x="110" y="40" width="80" height="28" rx="8" fill="#fdecec" stroke="#d94545" strokeWidth="1.5" /><text x="150" y="58" textAnchor="middle">checkout</text>
                <rect x="210" y="40" width="80" height="28" rx="8" fill="#fdecec" stroke="#d94545" strokeWidth="1.5" /><text x="250" y="58" textAnchor="middle">cart</text>
                <rect x="310" y="36" width="82" height="36" rx="8" fill="#fff6e0" stroke="#c58a12" strokeWidth="2" strokeDasharray="5 3" />
                <text x="351" y="52" textAnchor="middle">redis</text><text x="351" y="65" textAnchor="middle" fontSize="8.5" fill="#8a6100">candidate</text>
                <path d="M90 54H108" stroke="#c58a12" strokeWidth="2" markerEnd="url(#fa)" />
                <path d="M190 54H208" stroke="#c58a12" strokeWidth="2" markerEnd="url(#fa)" />
                <path d="M290 54H308" stroke="#c58a12" strokeWidth="2" markerEnd="url(#fa)" />
                <text x="10" y="22" fontSize="10" fill="#666">1 · anomalous services, linked by dependency paths</text>
                <rect x="10" y="100" width="185" height="80" rx="10" fill="#f6f6f6" />
                <text x="22" y="120" fontWeight="600">Evidence for redis</text>
                <text x="22" y="138" fill="#444">mem ↑ score 380</text>
                <text x="22" y="153" fill="#444">latency-90 ↑ score 33</text>
                <text x="22" y="168" fill="#444">explains 3 symptoms</text>
                <rect x="210" y="100" width="182" height="80" rx="10" fill="#f6f6f6" />
                <text x="222" y="120" fontWeight="600">Mitigation</text>
                <text x="222" y="138" fill="#444">restart redis · medium risk</text>
                <text x="222" y="153" fill="#444">approve → simulate</text>
                <text x="222" y="168" fill="#2f7a12">simulated: resolved → memory</text>
                <path d="M351 74V92H300" stroke="#999" strokeWidth="1.2" fill="none" markerEnd="url(#fg)" />
              </g>
            </svg>
            <p style={{ color: "#666", fontSize: 11, margin: "6px 0 0" }}>Illustration based on the scenario “Cart latency rising again”.</p>
          </div>
          <div>
            <h2>Where things are</h2>
            <dl className="fly-nav">
              <dt>Incidents</dt><dd>List, summary tiles, Investigate, and four tabs: Architecture &amp; Blast Radius, Root Cause &amp; Evidence, Mitigations, Historical Context</dd>
              <dt>Memory &amp; Timeline</dt><dd>Every stored repair outcome and a timeline of investigated incidents</dd>
              <dt>Evaluation</dt><dd>Benchmark metrics by mode and split</dd>
              <dt>Help (?)</dt><dd>The full guide</dd>
              <dt>FalkorDB pill</dt><dd>Green: graph reachable · red: unavailable</dd>
            </dl>
          </div>
        </div>

        <h2>Quick start</h2>
        <ul className="fly-check">
          <li>Check the FalkorDB pill (top right) is green.</li>
          <li>Pick an incident from the list; filter by Scenario or Benchmark.</li>
          <li>Choose a mode in the Investigation tile and press Investigate.</li>
          <li>Click the dashed amber node, the root cause candidate (unverified), to see its signals and blast radius.</li>
          <li>Compare hypotheses and their supporting and contradicting evidence in Root Cause &amp; Evidence.</li>
          <li>In Mitigations, approve a disruptive action if needed and press Simulate.</li>
          <li>Open Historical Context to see which past outcomes apply and which were rejected.</li>
        </ul>

        <div className="fly-foot">
          <span>Simulated actions never touch real infrastructure. Root causes are hypotheses until confirmed by you.</span>
          <span>Faultline · Incident Investigation</span>
        </div>
      </article>
    </div>
  );
}
