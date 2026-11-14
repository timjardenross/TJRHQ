# aci-vimeo notes (SOURCE-016, ACI "Chronic Pain" Vimeo channel)

Method: sequential curl (Mozilla UA, 1 s gaps) of the channel page and `https://vimeo.com/channels/pain/<id>` for all 57 ids (all HTTP 200). Title, duration and upload date came from the page JSON-LD VideoObject. The public `vimeo.com/api/v2/video/<id>.json` answered for 36 of 57 ids (21 returned 404, cause unknown); where it answered, description was empty and tags none.

Not possible, and not worked around:
- `vimeo.com/<id>` returns a human-verification challenge to curl.
- `player.vimeo.com/video/<id>/config` and the player page return 403 (domain-restricted), as does oEmbed (`domain_status_code` 403). So captions, text tracks and chapters were not inspected. Page markup shows `data-captions="true"` but that is not proof of a caption track, so `transcript_available` is `unknown` for every item.
- The ACI website is behind a bot challenge and was not touched.

Result: all 57 records are `metadata_verified` (title, duration, upload date, creator, URL). None is `content_reviewed`. Summaries, concepts, techniques, objectives, cautions and classification proposals are left empty because the page offers only Vimeo boilerplate descriptions. Title-only hints sit in `classification_proposals.title_hint_only` and should not be used as classification. Audience is not stated anywhere inspected, so it is unconfirmed for all three series. The only audience-related text is the channel description: "self management of your pain in partnership with your health care providers".

Total runtime 15,023 s (about 4 h 10 min): PainBytes 45, core 7, SCI 5. Upload dates 2014-02-17 to 2014-07-31.

Duplicates/overlaps: TMP-aci-0017 vs TMP-aci-0037 (same title stem, both 51 s) are probable duplicates; TMP-aci-0014 vs TMP-aci-0018 (both 110 s) are a possible overlap. Segment videos carry `series`, `episode` and `part_of` (parent episode intro; 5A-5D also point to the Segment 5 overview TMP-aci-0031). Gaps: PainBytes Ep5 lacks Segments 1-3; SCI series lacks Episodes 3 and 5.

Recommendations: obtain captions via the app origin or a Captain-approved route (or human viewing) before any content review; decide whether to keep the probable-duplicate E5 intro; flag the 2014 age of the content (medications, activity advice) for currency checks; embed test is still pending from the real app origin.
