# Adjudication pack — the five disputed ESCALATE labels (rubric 2.0 labels; recommendations under the Captain's 2026-11-23 rule)

Original reviewer labels are preserved unchanged in `tests/fixtures/labels_v2_reviewer{A,B}.json`; nothing here overwrites them. The
"recommended" column is a recommendation for the Captain's decision (the `captain_decision` columns in
`adjudication_v2_escalate_disagreements.csv` stay empty). Evidence below comes from the stored article summary or a page read on 2026-11-23, as stated.
Rule applied to the three South Australian items: the Captain's direction of 2026-11-23, *a credible report of a significant active regional
electricity outage of about 20,000 customers is a provisional ESCALATE; customer count is not a universal threshold; reassess on new evidence.*

| # | Event (id) | Reviewer A | Reviewer B | Evidence | Rubric rule | Recommended final |
|---|---|---|---|---|---|---|
| 1 | "Breaking: Transmission towers 'crushed', knocking out power to 20,000" — ABC News, 19 Nov (`735f41`) | W / medium ("regional") | E / high | Stored ABC summary: multiple transmission towers brought down by storms; more than 20,000 properties on South Australia's Eyre Peninsula without power. Contemporary report. | v2.0 "regional disruption is medium" is superseded by the Captain's rule for significant active regional electricity outages | **ESCALATE, provisional** |
| 2 | "11,000 still without power after storm cell topples transmission towers" — ABC News, 19 Nov (`4893fe`) | W / medium | E / high | Stored ABC summary: the main transmission line supplying the Eyre Peninsula may take days to restore; government seeking spare generation. Same incident as #1, an update with a lower, later count (restoration under way). | same rule; ongoing, restoration measured in days | **ESCALATE, provisional** (member of the same incident as #1 and #3) |
| 3 | "Live: Power still out after SA transmission line downed" — ABC News, 19 Nov (`12dbf4`) | W / medium | E / high | Stored ABC summary: swathes of the Eyre Peninsula remain without power after a storm knocked down major transmission towers. Same incident. | same rule; ongoing | **ESCALATE, provisional** (same incident) |
| 4 | "'All this food is now useless': Piles of rubbish after shop freezers hit by cyber-attack" — BBC News video, 3 Nov (`2fa557`) | E / high | W / medium | Stored BBC summary (page not re-read): dozens of supermarkets in seven European countries dumped huge quantities of food after refrigerators and freezers were targeted in a cyber-attack. The headline alone gives no scale. | Tier 2 (food supply); confirmed consequence with multi-country scale, but no store closures or supply interruption is stated; "unresolved consequences" is the VERIFY definition | **VERIFY** (judgement: upgrade to ESCALATE if closures or a supply interruption are reported; the alternative reading is WATCH) |
| 5 | "Container ship hit by projectile sinks in Strait of Hormuz, Singapore says" — BBC News, 14 Oct (`84bb81`) | E / high | V / medium | Page read 2026-11-23: GFS Pride sunk after a projectile strike; all 21 crew evacuated, no injuries; Singapore's port authority and Iran's Revolutionary Guards give different causes (projectile vs mines); UKMTO reports two other ships struck with minor damage; the Strait has been under repeated attack and partly closed since the war began. | No casualty or new essential-service interruption stated for this event; cause disputed (unresolved facts) | **VERIFY** (cascading effect on shipping is context, not stated for this event; upgrade if traffic disruption or casualties are reported) |

Notes
* #1–#3 are one incident. At incident level the recommendation is a single provisional ESCALATE for the Eyre Peninsula outage; all three reports are from one
  publisher, so independent corroboration is still 1, and the next action is to confirm customer count, affected area and restoration estimate with the network
  operator or regulator.
* Cases #4 and #5 are recommendations by judgement; reasonable reviewers could differ, which is the reason they are listed for the Captain.
* Model behaviour after the policy change: the detector now returns provisional ESCALATE for #1–#3 (`wk-detect/0.5.0-tiered-v2`, regional outage proportionality rule) and
  VERIFY or WATCH-level handling for #4 (Tier 2, no scale in the headline) and #5 (no sector recognised; physical event).
