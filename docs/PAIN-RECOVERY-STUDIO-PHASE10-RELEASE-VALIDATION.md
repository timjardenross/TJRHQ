# Pain Recovery Studio Phase 10 release validation

Version: 1.0  
Date: 14 November 2026  
Status: Engineering preparation complete; external gates remain open.

Phase 10 is the release-validation phase. It does not add another patient workflow. It proves that the Phase 9 journeys are usable, safe, accessible and trustworthy outside the test suite.

## Direct test routes

Use the deployed host when available:

- Studio start: `/pain-recovery-studio/start`
- Today: `/pain-recovery-studio`
- Start-my-day journey: choose the morning entry on Today
- Help-me-now journey: choose the immediate-help entry on Today
- Something-changed journey: choose the changed-day entry on Today
- Low energy: `/pain-recovery-studio/guide-me/low-energy`
- Overwhelmed: `/pain-recovery-studio/guide-me/overwhelmed`
- Activity support: `/pain-recovery-studio/activity`
- Safety card: `/pain-recovery-studio/safety`
- Crisis path: `/pain-recovery-studio/crisis`
- Learning: `/pain-recovery-studio/learn`
- Resources: `/pain-recovery-studio/resources`
- Human media: `/pain-recovery-studio/resources/human-media`
- Review: `/pain-recovery-studio/review`

## Gate 1: logged-in iPhone journey

Test on a real iPhone using the production host and an authenticated account.

- [ ] Open Today with a new day and see only the current step.
- [ ] Complete start my day without unnecessary scrolling.
- [ ] Return to Today and complete help me now.
- [ ] Trigger something changed and confirm it does not restart the day.
- [ ] Verify back, refresh and re-entry preserve the correct stage.
- [ ] Verify a missed day offers re-entry without catch-up pressure.
- [ ] Capture screen recording and any route, loading or state-loss defect.

Pass: all three journeys can be completed with one hand, no dead buttons, no unexpected 404s and no lost state.

## Gate 2: VoiceOver and keyboard

- [ ] Every interactive control has an accessible name.
- [ ] Focus is visible and moves in a logical order.
- [ ] Journey state changes are announced once and are not duplicated.
- [ ] The current step and remaining steps are announced.
- [ ] Safety and crisis content is reachable without relying on colour.
- [ ] Text remains usable at increased text size and landscape width.
- [ ] Keyboard users can open and close every disclosure and return to the trigger.

Pass: no task depends on sight, touch precision, colour or audio.

## Gate 3: clinical and content review

The reviewer must approve the exact rendered wording, not a screenshot or summary.

- [ ] Safety card wording reviewed by the nominated clinician.
- [ ] Phase 7 activity wording confirms Peter remains the exercise authority.
- [ ] New-symptom and flare boundaries are confirmed.
- [ ] External media transcript and captions are checked against the source.
- [ ] Resource owners, permissions, source URLs and review dates are recorded.

Pass: approval record names the reviewer, date, exact version and any exclusions.

## Gate 4: privacy and data handling

- [ ] Test with synthetic data first.
- [ ] Confirm consent copy before any external AI request.
- [ ] Confirm the no-consent authored fallback.
- [ ] Confirm local export and delete behaviour on-device.
- [ ] Confirm the account-level remote deletion boundary with the data owner.
- [ ] Confirm logs do not contain medications, clinician details or unnecessary free text.

Pass: no identifiable health data is used until the consent, retention and deletion decisions are recorded.

## Gate 5: five-day personal-use trial

- [ ] Day 1: normal or Green day.
- [ ] Day 2: low-energy or Amber day.
- [ ] Day 3: use help-me-now without opening the tracker first.
- [ ] Day 4: simulate a missed day and re-enter.
- [ ] Day 5: review learning and functional progress.

After each day record only:

1. Did the next action become clear within 30 seconds?
2. Did the Studio reduce effort or add effort?
3. Did any wording feel unsafe, blaming or overconfident?
4. What would you remove?

Pass: the experience remains useful on a low-capacity day and does not create a new monitoring obligation.

## Release decision

- **Go:** all five gates pass, with no unresolved Critical or High safety, privacy or accessibility defect.
- **Conditional go:** engineering passes, but only synthetic-data testing is permitted while an external gate remains open.
- **No-go:** any dead primary action, lost safety path, unsafe clinical wording, inaccessible essential task or unreviewed identifiable-data flow.

The current status is **Conditional go for validation only**. Engineering cannot mark the external gates complete from automated tests alone.
