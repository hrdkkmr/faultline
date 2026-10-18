import { BookOpen, X } from "lucide-react";
import { useState } from "react";
import { href } from "../lib/router";

const KEY = "faultline.guide.dismissed";

// Per-browser convenience only; if storage is unavailable the hint simply shows again.
export const markGuideSeen = () => { try { localStorage.setItem(KEY, "1"); } catch { /* storage blocked */ } };
const seen = () => { try { return localStorage.getItem(KEY) === "1"; } catch { return false; } };

/** One-time pointer to the guide for first-time users. Dismissing or opening the guide hides it for good. */
export default function GuideHint() {
  const [hidden, setHidden] = useState(seen);
  if (hidden) return null;
  const dismiss = () => { markGuideSeen(); setHidden(true); };
  return (
    <div className="guide-hint" role="note">
      <BookOpen size={16} aria-hidden />
      <span><b>New to Faultline?</b> A short guide walks through incidents, the graph, evidence and mitigations.</span>
      <a href={href({ page: "guide" })} onClick={markGuideSeen}>Open the guide</a>
      <button className="icon-btn" onClick={dismiss} aria-label="Dismiss guide hint" title="Dismiss"><X size={14} /></button>
    </div>
  );
}
