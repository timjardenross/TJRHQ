# Legacy route and compatibility quarantine

The `(app)` route family and LCARS compatibility components are retained only
for old bookmarks and external deep links. They are not part of the current
navigation architecture and must not receive new product capability.

## Rules

- New navigation points to `*-workbench`, `/hub`, `/briefs`, or the current
  task-family directory at `/workbenches`.
- A legacy route must either redirect to its canonical successor or render a
  clear “Compatibility route” notice with a link to the successor.
- Legacy components (`LCARSHeader`, `LCARSNav`, `LCARSBottomNav`,
  `LCARSPanel`, and `StatusBadge`) may support compatibility routes, but must
  not be imported into new workbench pages. `WorkbenchPanel` and
  `WorkbenchBadge` are the wb-native replacements purpose-built so
  `*-workbench` routes need never import anything LCARS-rooted (see
  `src/components/WorkbenchPanel.tsx`) — they are *not* legacy and are safe,
  expected imports in canonical workbench routes. (Corrected 2026-09-21
  acceptance pass: this document previously named `WorkbenchPanel`/
  `WorkbenchBadge` as the legacy pair by mistake, which would have made every
  canonical workbench importing them look like a violation.)
- Compatibility routes are non-indexable and must not be added to
  `LIVE_WORKBENCHES`.
- Before deleting a compatibility route, search for inbound links, external
  deep-link contracts, and API callers; record the successor in this document.

## Current quarantine

| Family | Canonical destination | Handling |
| --- | --- | --- |
| Legacy missions | `/mission-workbench` | Redirect, including detail IDs |
| Legacy capture | `/capture-workbench` | Query-preserving redirect |
| Legacy alerts | `/captains-chair-workbench/alerts` | Redirect |
| Legacy knowledge | `/knowledge-workbench` | Redirect |
| Legacy medical | `/human-systems-workbench/medical/*` | Redirect |
| Legacy brief | `/briefs` | Compatibility notice |
| Legacy communications | `/content-workbench` | Compatibility notice |
| Legacy intelligence | `/briefs`, `/intelligence-workbench`, `/content-workbench` | Compatibility notice |
| Legacy operations | Captain’s Chair, Capture, Engineering Handoffs | Compatibility notice |

The compatibility layout marks the family with
`data-route-family="legacy-compatibility"`, making accidental reuse easy to
detect in browser checks and future audits.
