import { ReactNode } from "react";

// Provenance tags: every claim in the UI is labeled with where it comes from.
export type Prov = "observed" | "architecture" | "trace" | "hypothesis" | "simulated" | "memory" | "truth" | "synthetic";

const LABEL: Record<Prov, string> = {
  observed: "observed",
  architecture: "architecture-derived",
  trace: "trace-observed",
  hypothesis: "agent hypothesis",
  simulated: "simulated outcome",
  memory: "memory",
  truth: "ground truth (eval only)",
  synthetic: "synthetic scenario",
};

export function Tag({ p, children }: { p: Prov; children?: ReactNode }) {
  return <span className={`tag tag-${p}`}>{children ?? LABEL[p]}</span>;
}

export function Legend() {
  return (
    <div className="legend">
      {(["observed", "architecture", "trace", "hypothesis", "simulated", "memory"] as Prov[]).map((p) => (
        <Tag key={p} p={p} />
      ))}
    </div>
  );
}

export function Panel({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="panel">
      <header>
        <h3>{title}</h3>
        {right}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="error" role="alert">{error}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function IdLink({ id, onOpen }: { id: string; onOpen: (id: string) => void }) {
  return (
    <button className="idlink" onClick={() => onOpen(id)} title="Inspect source record">
      {id}
    </button>
  );
}

export const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 1000) / 10}%`);
