import { ChevronRight, CircleAlert, LoaderCircle } from "lucide-react";
import { KeyboardEvent, ReactNode, useRef } from "react";
import { ApiError } from "../api";
import { statusLabel } from "../lib/format";

type Tone = "neutral" | "accent" | "good" | "warn" | "bad" | "candidate" | "sim" | "memory";

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>;
}

export function Dot({ tone = "neutral", title }: { tone?: Tone; title?: string }) {
  return <span className={`dot dot-${tone}`} title={title} aria-label={title} role={title ? "img" : undefined} />;
}

/** Text with a leading status dot: lighter than a pill badge for values repeated in lists. */
export function StatusText({ status }: { status: string }) {
  return <span className={`status-text st-${STATUS_TONE[status] ?? "neutral"}`}><i aria-hidden />{statusLabel(status)}</span>;
}

/** Tone-coloured inline text with a dot, for verdicts and risk in dense rows. */
export function Meta({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return <span className={`meta meta-${tone}`} title={title}><i aria-hidden />{children}</span>;
}

export function Spinner({ size = 14 }: { size?: number }) {
  return <LoaderCircle size={size} className="spin" aria-hidden />;
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return <div className="state"><Spinner /> {label}…</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="state muted">{children}</div>;
}

/** Concise error with the technical detail behind a disclosure. */
export function ErrorNotice({ error, action }: { error: unknown; action?: ReactNode }) {
  if (!error) return null;
  const e = error as Error;
  const summary = e instanceof ApiError ? e.message : "Something went wrong";
  const detail = e instanceof ApiError ? e.detail : e?.message ?? String(error);
  return (
    <div className="notice notice-bad" role="alert">
      <CircleAlert size={15} aria-hidden />
      <div className="notice-body">
        <span>{summary}</span>
        {detail && (
          <details>
            <summary>Details</summary>
            <code>{detail}</code>
          </details>
        )}
      </div>
      {action}
    </div>
  );
}

export function Disclosure({ title, children, defaultOpen = false, meta }: {
  title: ReactNode; children: ReactNode; defaultOpen?: boolean; meta?: ReactNode;
}) {
  return (
    <details className="disclosure" open={defaultOpen}>
      <summary>
        <ChevronRight size={14} className="chev" aria-hidden />
        <span className="disclosure-title">{title}</span>
        {meta && <span className="disclosure-meta">{meta}</span>}
      </summary>
      <div className="disclosure-body">{children}</div>
    </details>
  );
}

export function Section({ title, right, children, className = "" }: {
  title: ReactNode; right?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`section ${className}`}>
      <header className="section-head"><h3>{title}</h3>{right}</header>
      {children}
    </section>
  );
}

export interface TabDef<T extends string> { id: T; label: string; icon?: ReactNode; count?: number | null }

/** WAI-ARIA tabs with arrow-key navigation. */
export function Tabs<T extends string>({ tabs, value, onChange, label, size = "md" }: {
  tabs: TabDef<T>[]; value: T; onChange: (t: T) => void; label: string; size?: "md" | "sm";
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  function onKey(e: KeyboardEvent, i: number) {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const n = (i + d + tabs.length) % tabs.length;
    refs.current[n]?.focus();
    onChange(tabs[n].id);
  }
  return (
    <div className={`tabs tabs-${size}`} role="tablist" aria-label={label}>
      {tabs.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => { refs.current[i] = el; }}
          role="tab"
          aria-selected={t.id === value}
          tabIndex={t.id === value ? 0 : -1}
          className={t.id === value ? "tab active" : "tab"}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => onKey(e, i)}
        >
          {t.icon}{t.label}{t.count != null && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: { id: T; label: string }[]; value: T; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} role="radio" aria-checked={o.id === value} className={o.id === value ? "active" : ""} onClick={() => onChange(o.id)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function IconButton({ label, onClick, children, active, disabled }: {
  label: string; onClick: () => void; children: ReactNode; active?: boolean; disabled?: boolean;
}) {
  return (
    <button className={`icon-btn${active ? " active" : ""}`} onClick={onClick} title={label} aria-label={label}
      aria-pressed={active} disabled={disabled}>
      {children}
    </button>
  );
}

export function ScoreBar({ value, max = 1, label }: { value: number; max?: number; label: string }) {
  const w = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <span className="scorebar" title={`${label}: ${value.toFixed(2)}`}>
      <span className="scorebar-label">{label}</span>
      <span className="scorebar-track"><i style={{ width: `${w}%` }} /></span>
      <span className="scorebar-val">{value.toFixed(2)}</span>
    </span>
  );
}

export const OUTCOME_TONE: Record<string, Tone> = { resolved: "good", not_resolved: "warn", worsened: "bad" };
export const VERDICT_TONE: Record<string, Tone> = {
  recommended: "good", not_recommended: "bad", needs_more_evidence: "warn",
  applicable: "good", partial: "warn", rejected: "bad",
};
export const RISK_TONE: Record<string, Tone> = { low: "neutral", medium: "warn", high: "bad" };
export const STATUS_TONE: Record<string, Tone> = {
  open: "accent", investigated: "neutral", resolved: "good", mitigation_failed: "bad",
};
