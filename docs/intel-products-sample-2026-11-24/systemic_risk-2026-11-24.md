# Cross-sector and systemic provider view, generated 2026-11-24

Source: export files given on the command line. Window: 2026-08-26 to 2026-11-24. Offline, read-only, default OFF, not wired into any service. Taxonomy and tagger: PR #706 (`provider_involvement`), text only, own-feed tagging off.

Labels: [OBSERVED FACT] counted/read from stored rows | [PLAUSIBLE RELATIONSHIP] consistent with the data, mechanism not shown | [UNVERIFIED HYPOTHESIS] needs outside evidence. Coincident trends are never treated as causation; no organisation is asserted to depend on any provider without evidence.

## Evidence base

- [OBSERVED FACT] 523 items in window; tags: DIRECTLY_INVOLVED 135, MENTIONED 383, UNCERTAIN 5.
- [OBSERVED FACT] Items with a populated `organisation` field: 0 of 523.
- [OBSERVED FACT] AFFECTED tags: 0; SUPPLYING tags: 0.
- [OBSERVED FACT] AU critical-infrastructure cut (geography AU, sector in energy/transport/financial_services/technology, event type in technology_outage/third_party_disruption/energy_disruption/transport_disruption/cyber): 100 items; tags DIRECTLY_INVOLVED 57, MENTIONED 42, UNCERTAIN 2; AFFECTED 0, SUPPLYING 0.

## Shared-provider concentration

**INSUFFICIENT EVIDENCE. No concentration score is produced.** Not assessed: insufficient evidence; this is NOT evidence of low concentration risk. Required: at least 3 distinct organisations, each with item-level AFFECTED or SUPPLYING evidence naming the same provider, across at least 2 independent events, plus a public source for each organisation-specific link. Found: 0 AFFECTED and 0 SUPPLYING tags in the window, 0 items with an organisation value, and 0 AFFECTED/SUPPLYING tags among the 100 AU critical-infrastructure items.

Telstra and Optus recurrence in this corpus is repeated news about single-provider outages. It is not shared-provider concentration.

## Provider-involvement links across 2+ sectors (episodes at least 7 days apart)

Rule (precision first): the same provider is DIRECTLY_INVOLVED, with a strong incident clause, in two separate episodes (reports less than 7 days apart are one event), and the item text itself names a different sector in each episode (bank/payments, energy, transport, telecoms, health, government). Classifier sector labels are never used as evidence. Events whose type is 'other' are ignored. A link shows reported involvement, not that any sector depends on the provider.

Organisation rule (3+ named organisations): 0 links, because `organisation` is populated on 0 items. Insufficient evidence for any organisation-based link.

No sector-spanning links found.

## Limits

- Reported involvement, not dependency: every tag carries `dependency_proven = False`.
- The tagger is deterministic and conservative; PR #706 measured about 77% strict class precision and did not measure recall. Many involvements are filed as MENTIONED or UNCERTAIN and so never reach this view.
- Episodes are separated by time only (7 days), so one long-running event can still be split in two, and a real second event within 7 days is merged. Recall is low by design.
- The export is a sample, with a heavy Telstra news share and no organisation values.
- [UNVERIFIED HYPOTHESIS] Whether any sector would be affected by a provider failure is not inferred.
