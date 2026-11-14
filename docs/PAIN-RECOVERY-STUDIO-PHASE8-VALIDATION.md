# Pain Recovery Studio Phase 8 Validation

Version: 1.0  
Date: 14 November 2026  
Status: Engineering validation complete; real-user and clinician checks remain external gates.

## Release scenarios

| Scenario | Expected result | Engineering status |
| --- | --- | --- |
| First use without consent | Authored guidance remains available; remote storage is not implied | Pass by route contract and tests |
| Consent granted | Remote session and learning writes are available | Pass by API contract and tests |
| Consent withdrawn | Remote learning is refused; local fallback remains clear | Pass by API contract; device test pending |
| Safety or crisis language | Static safety response; no model call | Pass by deterministic route guard |
| New or concerning symptom | Safety hold and safety card path | Pass by guard and UI route |
| AI unavailable | Authored fallback remains usable | Pass by route fallback |
| Missed days | Re-entry without catch-up | Pass by companion tests |
| Activity pause | No exercise modification; Peter remains authority | Pass by Phase 7 route tests |
| External media unavailable | Source page and text/transcript fallback remain available | Pass by media route design |
| Export/delete learning | User can export or remove local learning data | Pass locally; remote deletion remains account-governed |

## Safety invariants

- The Studio does not diagnose or decide whether a symptom is dangerous.
- Crisis and safety language bypasses Gemini.
- Safety hold outranks activity coaching.
- Peter’s exercise plan outranks Studio guidance.
- The Studio does not prescribe, progress or compensate for exercise.
- Observed patterns are not presented as clinical causes.
- Medication and diagnosis fields are not added to learning records.

## External validation still required

1. Logged-in iPhone journey test.
2. VoiceOver and keyboard test.
3. Clinician review of the safety card and Phase 7 activity wording.
4. Manual verification of every external transcript and caption.
5. Multi-day personal-use test of the learning loop.

## Go/no-go rule

Engineering may mark Phase 8 software validation passed when typecheck, focused tests, full regression and production build pass. The product remains conditional for personal rollout until the five external checks above are completed.
