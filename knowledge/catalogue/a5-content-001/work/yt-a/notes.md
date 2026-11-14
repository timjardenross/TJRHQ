# yt-a notes (SOURCE-001, 002, 004, 010)

Method: curl (sequential, Mozilla UA) on channel /videos, /playlists, /about, uploads playlist (UU...) and each channel playlist; parsed server-rendered ytInitialData. 758 unique video ids enumerated.

Not possible:
- Watch pages hit a Google bot-protection redirect; not bypassed. No descriptions, chapters, exact dates, caption flags or transcripts. All 118 assets are metadata-level (`discovered`), summaries null.
- RSS 404 for all channel IDs. Internal browse-API pagination refused by permission system; not retried. Enumeration partial except Diggin' the Dharma (53/53).
- Dates only relative; recency window applied from buckets (7y+ excluded, 100 Doug's Dharma videos).

Key finding: registered SOURCE-002 channel ID is Diggin' the Dharma, not Doug's Dharma (UCPIyEJzvW7SsbiIrooixjNA). Both covered.

Recommendations: fix register; allow a route for descriptions/captions (watch-page access or Captain-approved API/yt-dlp metadata) before content review; confirm relevance of title-keyword candidates; SOURCE-001/010/004 are low pain-relevance.
