// Guide structure, shared by the guide page and the printable flyer. Section ids are URL fragments (#/guide/<id>).

export const SECTIONS = [
  { id: "start", letter: "A", title: "Getting started" },
  { id: "investigate", letter: "B", title: "Investigating an incident" },
  { id: "graph", letter: "C", title: "Exploring the graph" },
  { id: "evidence", letter: "D", title: "Understanding evidence" },
  { id: "mitigations", letter: "E", title: "Reviewing mitigations" },
  { id: "memory", letter: "F", title: "Using historical memory" },
  { id: "evaluation", letter: "G", title: "Evaluation" },
  { id: "troubleshooting", letter: "H", title: "Troubleshooting" },
] as const;

export const WORKFLOW = [
  { n: 1, t: "Select", d: "Pick an incident", s: "start" },
  { n: 2, t: "Investigate", d: "Run the graph investigation", s: "investigate" },
  { n: 3, t: "Explore", d: "Trace dependencies", s: "graph" },
  { n: 4, t: "Weigh evidence", d: "Compare hypotheses", s: "evidence" },
  { n: 5, t: "Mitigate", d: "Simulate a repair", s: "mitigations" },
  { n: 6, t: "Learn", d: "Reuse past outcomes", s: "memory" },
] as const;
