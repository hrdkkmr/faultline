import type { GraphEdge, GraphNode } from "../../api";

/**
 * Layered left-to-right layout derived from DEPENDS_ON edges: each service sits one column to the
 * right of its deepest caller, so dependency direction always reads left -> right. Within a column,
 * nodes are ordered by the mean row of their callers (barycenter) to reduce edge crossings.
 */
export function layered(nodes: GraphNode[], edges: GraphEdge[], colGap = 200, rowGap = 62) {
  const names = nodes.map((n) => n.name);
  const deps = edges.filter((e) => e.type === "DEPENDS_ON");
  const callers: Record<string, string[]> = Object.fromEntries(names.map((n) => [n, []]));
  deps.forEach((e) => callers[e.target]?.push(e.source));

  const layer: Record<string, number> = {};
  const visiting = new Set<string>();
  const depth = (n: string): number => {
    if (layer[n] != null) return layer[n];
    if (visiting.has(n)) return 0; // cycle guard
    visiting.add(n);
    const d = callers[n].length ? Math.max(...callers[n].map(depth)) + 1 : 0;
    visiting.delete(n);
    return (layer[n] = d);
  };
  names.forEach(depth);

  const cols: string[][] = [];
  names.forEach((n) => (cols[layer[n]] ||= []).push(n));
  const row: Record<string, number> = {};
  cols.forEach((col) => {
    const bary = (n: string) => {
      const ps = callers[n].filter((p) => row[p] != null);
      return ps.length ? ps.reduce((a, p) => a + row[p], 0) / ps.length : 0;
    };
    col.sort((a, b) => bary(a) - bary(b) || a.localeCompare(b));
    col.forEach((n, i) => (row[n] = i - (col.length - 1) / 2));
  });

  const pos: Record<string, { x: number; y: number }> = {};
  names.forEach((n) => (pos[n] = { x: layer[n] * colGap, y: row[n] * rowGap }));
  return pos;
}
