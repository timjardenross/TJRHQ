# A5-CONTENT-001 content-review protocol (for review sub-agents)

Mission: USS-TJR-MSN-0511. Read `knowledge/missions/A5-CONTENT-001-recovery-multimedia-catalogue-brief.md` (sections 4, 5, 6, 9) and `knowledge/catalogue/a5-content-001/source-register.json` and `asset-inventory.json` (for record shape) first.

## Goal
Enumerate EVERY relevant video/audio item from your assigned sources and record each at asset level with verified information. Cover the whole source (all playlists/pages), not a sample. Quality over invention: unknown stays unknown.

## Hard rules
- Never fabricate titles, durations, dates, transcript text, timestamps, chapters or claims. Only record what you actually fetched/inspected. Unknown = null.
- Do NOT bypass bot protection/Cloudflare/login walls, spoof origins, download or proxy video, or strip restrictions. If blocked, record the block and move on.
- No Reddit. No paywalled, registration-gated or trial-gated items (record them as `rejected` with reason `requires_payment_or_login`).
- Don't classify from the title alone. Summaries/topics only from inspected description, chapters, captions or transcript; set `inputs_inspected` honestly. If only title+description were inspected, say so and keep the summary short.
- Transcript text: do not store. Record `transcript_available` (true/false/unknown), `transcript_kind` (publisher_captions | auto_captions | none | unknown) and, where you read it, produce a source-grounded summary with `source_spans` (timestamps or quoted short phrases, max 15 words each). Timestamps/chapters only if actually listed by the publisher.
- Clinical review is ALREADY DONE by the Captain's side: do NOT route anything to clinical review and do not use `clinical_review_required` as a status. Still record notable clinical claims, limitations and contraindications you actually saw in `clinical_cautions` (with a quote/span) as plain information for Gemini's explanations; this is not a gate. Set `review_status` to one of: discovered, metadata_verified, content_reviewed, rejected, unavailable. Use `rejected` only for off-scope, paywalled/login-gated or unavailable items. NEVER set `approved` (approval is a governance step the Captain controls).
- Relevance: keep items relevant to chronic pain self-management/recovery (brief section 5 taxonomy). Off-topic items go in `excluded` with a reason (not in `assets`).
- Capacity (Green/Amber/Red/any), topics, user_needs: record as PROPOSALS with a one-line rationale in `classification_proposals`; humans decide.
- Embed testing is deferred by Captain decision: always `embed_verified: false`; `delivery` = "external_link_fallback" unless the publisher states embedding is allowed.
- Rights: record platform terms and any copyright/licence text you actually saw; else "unknown".
- Be polite to servers: sequential requests, modest volume, a Mozilla user agent is fine. Tools: curl via Bash, WebFetch, WebSearch. Network is an allowlist; if a host is blocked note it in `issues` (don't try to work around it).
- Work ONLY inside your own output directory. Do not run git commands. Do not edit other files.

## Output (in `knowledge/catalogue/a5-content-001/work/<your-agent-id>/`)
- `assets.json`: {"source_ids": [...], "assets": [record...], "excluded": [{title,url,reason}], "issues": [...], "coverage": {"enumerated": n, "reviewed_with_content": n, "method": "..."}}
- `notes.md`: short methods, what could not be done and why, recommendations.
Record shape (extend the asset-inventory.json shape): asset_id (use `TMP-<agent>-NNNN`; I assign final IDs), source_id, title, creator, platform, media_type, source_url, platform_id, duration_seconds, published_at, description_excerpt (<=300 chars), language, chapters (publisher-listed only: [{start_seconds,title}]), transcript_available, transcript_kind, inputs_inspected, summary, learning_objectives, key_concepts, practical_techniques, clinical_cautions, classification_proposals {topics, user_needs, content_type, engagement_demand, capacity_suggested, capacity_rationale, attention_focus, physical_requirements, experience_level}, intended_audience, login_required, embed_verified:false, delivery, reuse_permission, attribution, review_status, last_verified_at ("2026-11-14").
Final reply: counts (enumerated/recorded/excluded), top issues, anything needing a Captain decision.
