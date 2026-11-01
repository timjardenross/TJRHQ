# Cross-portal command model

Every consequential workbench surface should be expressible as one command
record with five fields:

| Field | Contract |
| --- | --- |
| `action` | The single user-facing verb and intended outcome. |
| `evidence` | The source, observation time, confidence, and availability state supporting the action. |
| `state` | The current lifecycle state: pending, in progress, blocked, complete, failed, or unavailable. |
| `owner` | The actor responsible for the next transition: Captain, HQ, Number One, or an external dependency. |
| `freshness` | The age or freshness class of the evidence: current, aging, stale, or unknown. |

The UI must show the action first, then state and owner, with evidence and
freshness adjacent to the claim. A missing value is rendered as unknown or
unavailable; it is never inferred as healthy, complete, or current.

Task analytics are descriptive signals derived from real task records:
friction points (blocked, paused, or deferred), abandonment, retries/deferrals,
and time-to-completion from `started_at` to `completed_at`. They identify where
to investigate; they do not establish cause or user intent.
