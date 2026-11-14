# yt-b notes (A5-CONTENT-001, SOURCE-005..008)

## Method
- Public YouTube channel `/search?query=`, `/videos` and `/playlists` pages fetched with curl (Mozilla UA, sequential, ~1 s spacing); `ytInitialData` parsed for title, video id, duration, relative age, description snippet.
- Channel-scoped queries. SOURCE-005: pain, chronic pain, anxiety, stress, mindfulness, meditation, acceptance, sleep, insomnia, burnout, energy, values, breathing, grounding, nervous system, emotional regulation, suffering, body, fatigue. SOURCE-006: pain, chronic pain, chronic symptoms, symptoms, pacing, sleep, breathing, grounding, acceptance, mindfulness, hypervigilance, fatigue, nervous system, stress, panic, fear, body sensations, values. SOURCE-007: pain, chronic pain, back pain, neck pain, sciatica, sleep, insomnia, stress, anxiety, breathing, meditation, energy, fatigue, nervous system, vagus, acupressure, fibromyalgia, headache, inflammation, qi gong. SOURCE-008: pain, chronic pain, pain management, pain psychology, mindfulness, meditation, sleep, stress, anxiety, breathing, acceptance, opioid, back pain, fibromyalgia, nerve pain, neuropathy, integrative, physical therapy, pacing, fatigue.
- Relevance selected from title + listing snippet only; everything else is in `excluded` with a reason. Captain recency rule applied (>=7y ago per listing text -> `outside_recency_window`; `recency_band` on kept records).

## What could not be done
- `youtube.com/watch` is refused by the agent proxy (403) and WebFetch cannot resolve youtube.com, so no video was content-reviewed: no full description, chapters, caption flag, exact publish date or transcript. All 198 records are `discovered`, summaries say so, topics are provisional. `published_at` is null; relative age kept in `published_relative_listing`.
- RSS feeds returned 404. Playlists not enumerated. Search is fuzzy and `/videos` shows only 30 newest, so this is search-term coverage, not a full crawl.
- Banding from relative age ("5y ago" etc.) can be off by up to a year at the cutoff.

## Register errors found
- SOURCE-005 channel_id UCrGYoowsH-aKfSCM5TOzAsA is @HealthyGamerFamilies; real @HealthyGamerGG = UClHVl2N3jPEbkNJVx-ItQIQ.
- SOURCE-007 channel_id UCix7wE05YbRdOVUPNHy0KTg is @ModernHealthMonk; real @DrAlexHeyne = UCC3f6x4z_1SUQ0nvBGC55Hw.
- Both fixes were applied here; the register should be corrected.

## Recommendations
- Allow `www.youtube.com/watch` (or provide a transcript/metadata route) so a follow-up pass can read descriptions, chapters, captions and dates and do real content review.
- Shorts (<3-5 min) were excluded as thin; revisit if short clips are wanted.
- Heyne (TCM) and Kassam (paid programme links) clinical claims are recorded only as title-level cautions; not routed to clinical review per instruction.
