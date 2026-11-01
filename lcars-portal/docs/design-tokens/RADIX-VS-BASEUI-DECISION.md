# Radix Primitives vs Base UI — decision for ApprovalQueue.tsx

## What ApprovalQueue actually needs

Read the component before assuming anything from the survey. It has **no modal, no dropdown menu, no tooltip**. The only stateful interactive pattern is: clicking "Reject" swaps the Approve/Reject row for an inline reason-input + Confirm/Cancel row, per list item (`rejectReasonFor === item.id`). That is a **disclosure/collapsible region**, not a dialog — it never overlays content, never traps focus outside the list item, and Escape does nothing today.

The rest (Approve, Refresh, Confirm Reject, Cancel) are plain single-action buttons. Native `<button>` is already the correct accessible element for those; there's no primitive to swap in for "a button that does one thing on click." The real accessibility gap is that the disclosure toggle (Reject button) carries no `aria-expanded`/`aria-controls`, and the revealed region isn't marked as a live region tied to its trigger.

So the only primitive actually needed here is a **Collapsible** (Radix) / equivalent disclosure primitive (Base UI has no direct "Collapsible" — closest is `Collapsible` too, same shape, newer).

## Bundle size

- `@radix-ui/react-collapsible`: ~2.5kB gzipped on its own (plus `@radix-ui/react-primitive` + `@radix-ui/react-id` + `@radix-ui/react-use-controllable-state` as shared deps, a few more kB, largely amortized once other Radix primitives get adopted per the follow-up queue).
- Base UI `Collapsible`: comparable raw size, but Base UI is younger (public beta), smaller ecosystem, and its React 18 support is secondary to its React 19 concurrent-feature focus. This repo is pinned to React 18.3.1 / Next 14.2 — not on the React 19 track.

## Decision: Radix Primitives

Reasons:
1. Only `@radix-ui/react-collapsible` is needed for this file — smallest possible surface, no kitchen-sink install.
2. Mature, stable API (Radix Primitives predates Base UI by years), first-class React 18 support matching this repo's actual dependency versions.
3. The follow-up queue (10 more files, likely needing Dialog/DropdownMenu/Tooltip per the original survey) is far better served by Radix's breadth and longer track record than Base UI's newer, smaller primitive set.
4. Both preserve the "unstyled, bring your own classes" contract this migration needs (keep `wb-*`/token classes untouched) — Radix's `asChild` prop is well-documented and exactly what's used below.

Base UI was not chosen — it's a reasonable library but offers no concrete advantage for this repo's actual (React 18, single-Collapsible) need, and choosing it here would mean two different primitive libraries in the codebase since the follow-up queue's own needs (Dialog/DropdownMenu) point back to Radix anyway.
