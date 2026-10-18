import { useEffect, useState } from "react";

export type Page = "incidents" | "memory" | "evaluation" | "guide";
export type IncidentTab = "graph" | "evidence" | "mitigations" | "history";
export const TABS: IncidentTab[] = ["graph", "evidence", "mitigations", "history"];

export interface Route { page: Page; incident: string | null; tab: IncidentTab; section: string | null }

export function parse(hash: string): Route {
  const [page, a, b] = hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  if (page === "memory" || page === "evaluation") return { page, incident: null, tab: "graph", section: null };
  if (page === "guide") return { page, incident: null, tab: "graph", section: a || null };
  return {
    page: "incidents",
    incident: a || null,
    tab: TABS.includes(b as IncidentTab) ? (b as IncidentTab) : "graph",
    section: null,
  };
}

export function href(r: Partial<Route> & { page: Page }): string {
  if (r.page === "guide") return r.section ? `#/guide/${r.section}` : "#/guide";
  if (r.page !== "incidents") return `#/${r.page}`;
  if (!r.incident) return "#/incidents";
  return `#/incidents/${encodeURIComponent(r.incident)}${r.tab && r.tab !== "graph" ? `/${r.tab}` : ""}`;
}

export const go = (r: Partial<Route> & { page: Page }) => { window.location.hash = href(r); };

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

/** Shared by animations in JS (Cytoscape) so they honour the OS reduced-motion setting too. */
export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
