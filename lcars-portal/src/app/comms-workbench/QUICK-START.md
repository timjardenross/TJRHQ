# Using the TJR Design System in Comms Workbench

## Quick Start

Nothing to install — the library lives in this same repo at
`lcars-portal/src/components/ui/`.

```tsx
import { Button, Card, Badge, Tabs } from '@/components/ui';
```

## What changed in this page

`comms-workbench/page.tsx` previously used an ad-hoc, one-off color palette
(`#18223a`, `#61718c`, `#d9e1f0`, `#243b7a`) instead of the `wb.*` design tokens used
everywhere else in the portal. The tab nav has been replaced with the shared `Tabs`
component so it now matches the rest of the app and picks up focus-visible states,
`aria-current`, and the `wb-sage-deep` accent for free.

## Reference

- Design tokens: `../../../../../TJR-DESIGN-TOKENS.md` (repo root `TJR-DESIGN-TOKENS.md`)
- Component overview: repo root `TJR-DESIGN-SYSTEM-README.md`
- Live examples in this codebase: `intelligence-workbench/_components/Shell.tsx`,
  `intelligence-workbench/brief/[id]/page.tsx`, `intelligence-workbench/escalation/[id]/page.tsx`

## Common patterns

```tsx
// Tab navigation
<Tabs tabs={TABS} active={tab} onChange={selectTab} ariaLabel="Communications Workbench sections" />

// Status badge from a risk/severity string
<Badge status={riskToStatus(item.risk)}>{item.risk}</Badge>

// Primary action
<Button variant="primary" onClick={handleSubmit}>Approve</Button>

// Section card
<Card title="Pipeline">{children}</Card>
```
