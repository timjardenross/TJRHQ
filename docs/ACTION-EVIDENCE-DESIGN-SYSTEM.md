# Unified Action & Evidence Design System

This is the contract for every live USSTJR workbench. It applies to cards,
detail routes, queues, empty states, and consequential mutations.

## Action contract

Every workbench exposes one semantic primary action in the first viewport.
The label is a verb and describes the next user decision, for example
`Review active alerts`, `Start focus session`, or `Choose what to do next`.

Actions have four parts:

| Part | Requirement |
| --- | --- |
| Intent | One clear user outcome; never a generic `Open` or `Submit` when a more precise verb is available. |
| Scope | The action identifies the item or queue it affects. |
| Confirmation | Consequential, irreversible, or externally visible actions require an explicit confirmation or review step. |
| Outcome | Success, failure, and in-progress feedback use `ActionOutcome` or an equivalent live status with `aria-live`. |

Use `PRIMARY_ACTIONS` in `src/lib/workbenches.ts` for the workbench-level
action. Use the existing domain action controls for item-level actions. Do
not create a second competing primary action in the same viewport.

Consequential actions must also append a server-backed `audit_events` record
through `/api/action-history` with `category`, `actor`, `action`, `outcome`,
and structured `details`. Local storage may supplement continuity, but is
never the source of truth for action history.

## Evidence contract

Any data-bearing card or detail route must show evidence metadata close to the
claim it supports. Use `EvidenceMeta` with as many real values as are
available:

| Field | Meaning |
| --- | --- |
| Source | The actual system, feed, registry, or synthesis that produced the data. |
| Observed | The source observation or collection time, not the page render time. |
| Confidence | A real source confidence, coverage ratio, or explicit unavailable state. |

Never fabricate a timestamp or confidence value. If the source is unavailable,
use `DataAvailabilityNotice` with exactly one of `empty`, `no-action`,
`unavailable`, or `stale`. Do not represent an unavailable source as an empty
result.

## Required state model

Every data-bearing surface handles loading, success, empty, no action,
unavailable, stale, and error states. Colour is supplemental: the text and
status semantics must remain understandable without colour.

## Accessibility and interaction

Primary and consequential controls are native links or buttons, keyboard
reachable, have visible focus treatment, and expose state changes through
`aria-live` where appropriate. Destructive or externally visible actions must
not be triggered by navigation alone.

## Governance rules

The machine-readable governance registry lives in
`lcars-portal/src/lib/designGovernance.ts`. It is the review authority for
terms, status tones, density, and primary actions.

### Terms

Use the canonical labels `LifeOS Hub`, `Briefs`, `Emergency Alerts`, and
`Human Systems`. Do not introduce retired labels such as `Home`, `Captain's
Brief`, `Alerts`, or `Medical` for current surfaces. Lifecycle labels use
`Needs action`, `Awaiting owner`, `No action needed`, `Unavailable`, and
`Stale`.

### Status colours

Use `stateToneClasses`/`Badge` and the canonical state-to-badge mapping. The
operational state tone communicates status, never department identity. Text,
icons, and ARIA semantics must carry the meaning without colour.

### Density

Every new surface chooses one density deliberately: `comfortable` for
decision reading, `compact` for queues, or `data-dense` for deliberately
scannable tables. Dense layouts must use progressive disclosure on mobile and
must not reduce the target size or focus visibility of controls.

### Primary actions

Every live workbench has exactly one semantic first-viewport primary action,
registered in `PRIMARY_ACTIONS`. It must be a specific verb describing the
next decision—not a generic `Open`, `Go`, `Click`, or `Submit`. The
`validatePrimaryAction` contract is required in workbench registry tests.

## Review checklist

- [ ] One semantic primary action is present in the first viewport.
- [ ] Action outcome is visible and announced.
- [ ] Consequential action is recorded server-side.
- [ ] EvidenceMeta is present beside every material data claim.
- [ ] Source, observed time, and confidence are real or explicitly unavailable.
- [ ] Empty, no-action, unavailable, stale, loading, and error states are distinct.
- [ ] Primary controls are keyboard reachable with visible focus.
- [ ] Canonical terms, state tones, density, and primary-action rules pass the governance registry tests.
