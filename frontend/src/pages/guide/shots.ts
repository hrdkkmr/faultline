// Screenshots of the running application (1510×812, captured in Chrome from the live backend; see docs/guide.md).
// Marker positions are percentages of the image, measured from the elements' bounding boxes at capture time.
// When the UI changes, recapture the image and re-measure, otherwise the markers will point at the wrong place.

export interface Shot {
  src: string; w: number; h: number; alt: string; caption: string;
  markers: { n: number; x: number; y: number }[];
  /** Region of the image to show, in percent of the full image. Markers stay in full-image percent. */
  crop?: { x: number; y: number; w: number; h: number };
}

export type ShotId = "overview" | "investigate" | "graph" | "evidence" | "mitigations" | "history" | "evaluation";

const W = 1510, H = 812;

export const SHOTS: Record<ShotId, Shot> = {
  overview: {
    src: "guide/overview.jpg", w: W, h: H, caption: "Incidents page",
    alt: "Incidents page: incident list on the left, summary tiles and dependency graph on the right",
    markers: [{ n: 1, x: 8, y: 15.7 }, { n: 2, x: 6.9, y: 38.4 }, { n: 3, x: 82.2, y: 4.8 }, { n: 4, x: 2.9, y: 12.4 }],
  },
  investigate: {
    src: "guide/overview.jpg", w: W, h: H, caption: "Summary tiles and the Investigation tile", crop: { x: 25, y: 11, w: 74.5, h: 29 },
    alt: "Summary tiles for anomalous services, blast radius and root cause candidate, next to the Investigation tile",
    markers: [{ n: 1, x: 26.8, y: 23.6 }, { n: 2, x: 79.7, y: 32.1 }, { n: 3, x: 90, y: 32.1 }, { n: 4, x: 61.3, y: 23.6 }],
  },
  graph: {
    src: "guide/graph.jpg", w: W, h: H, caption: "Architecture & Blast Radius tab with redis selected", crop: { x: 25, y: 40, w: 75, h: 60 },
    alt: "Dependency graph with the redis root cause candidate selected and its details drawer open",
    markers: [{ n: 1, x: 27.4, y: 51.7 }, { n: 2, x: 78.2, y: 50.7 }, { n: 3, x: 74.8, y: 85.6 }, { n: 4, x: 26.5, y: 45.1 }],
  },
  evidence: {
    src: "guide/evidence.jpg", w: W, h: H, caption: "Root Cause & Evidence tab", crop: { x: 25, y: 8, w: 75, h: 92 },
    alt: "Ranked hypotheses beside the selected hypothesis with score bars, supporting evidence and evidence paths",
    markers: [{ n: 1, x: 27.3, y: 22.9 }, { n: 2, x: 47.3, y: 24.4 }, { n: 3, x: 47.3, y: 42.9 }, { n: 4, x: 47.3, y: 65.6 }],
  },
  mitigations: {
    src: "guide/mitigations.jpg", w: W, h: H, caption: "Mitigations tab", crop: { x: 25, y: 31, w: 75, h: 69 },
    alt: "Candidate actions with verdict, risk, approval and memory effect, one expanded to show its preconditions",
    markers: [{ n: 1, x: 43, y: 43.2 }, { n: 2, x: 27, y: 47.7 }, { n: 3, x: 85.4, y: 43.2 }, { n: 4, x: 71.4, y: 43.2 }],
  },
  history: {
    src: "guide/history.jpg", w: W, h: H, caption: "Historical Context tab", crop: { x: 25, y: 18, w: 75, h: 82 },
    alt: "An applicable and a rejected memory with reasons, related incidents, actions and investigation runs",
    markers: [{ n: 1, x: 27, y: 31.5 }, { n: 2, x: 63.6, y: 32.5 }, { n: 3, x: 27, y: 80.9 }],
  },
  evaluation: {
    src: "guide/evaluation.jpg", w: W, h: H, caption: "Evaluation page", crop: { x: 5, y: 7, w: 95, h: 93 },
    alt: "Headline metric cards for the test split and the results-by-mode table",
    markers: [{ n: 1, x: 7.4, y: 16.8 }, { n: 2, x: 75.6, y: 34.4 }],
  },
};
