# In-app guide: structure and maintenance

The "How to use Faultline" guide is part of the frontend, at `#/guide`. Open it from the **?** at the bottom of the
navigation rail or from **How to use** in the top bar. First-time visitors also see a one-time hint above the
incident workspace. It is dismissed per browser (`localStorage` key `faultline.guide.dismissed`) and never
reappears after the guide has been opened.

| Piece | File |
|---|---|
| Sections (A–H) and the six-step workflow | `frontend/src/pages/guide/content.ts` |
| Guide page | `frontend/src/pages/guide/GuidePage.tsx` |
| Printable one-pager (`#/guide/print`) | `frontend/src/pages/guide/Flyer.tsx` + `@media print` in `styles.css` |
| Screenshot registry (crop + numbered markers) | `frontend/src/pages/guide/shots.ts` |
| Screenshots | `frontend/public/guide/*.jpg` |

## Rules the guide follows
- It describes only controls that exist. Unavailable things are stated as unavailable ("Verified" outcomes, for
  example, because nothing ever runs on real infrastructure).
- Deep links point at real views. Incident links use the last incident viewed, otherwise an investigated scenario
  taken from `/api/incidents`, so they never name an incident that is not in the graph.
- The flyer's diagram is labelled as an illustration. Its numbers come from the scenario "Cart latency rising
  again" (`SYN-redis-mem-2`).

## Recapturing screenshots after a UI change
1. Run the backend and `npm run dev`, then open each view at a 1536×826 CSS-pixel viewport. The current images
   were captured at that size and saved at 1510×812. Captured views: the incident `SYN-redis-mem-2` (graph tab with
   redis selected, evidence, mitigations with the first row expanded, history) and `#/evaluation`.
2. For each marker, measure the target element in the browser console:
   `r = el.getBoundingClientRect(); [(r.left + r.width*fx) / innerWidth * 100, (r.top + r.height*fy) / innerHeight * 100]`.
3. Update `markers` (and `crop` if the layout moved) in `shots.ts`.

## Printing
**Print** on `#/guide/print` opens the browser's print dialog; choose "Save as PDF" for a file. There is no PDF
generator in the app. To check the layout from the command line:
`chrome --headless=new --print-to-pdf=flyer.pdf --no-pdf-header-footer --virtual-time-budget=8000 "http://localhost:5173/#/guide/print"`
(this produced one A4 page on 2026-10-18).
