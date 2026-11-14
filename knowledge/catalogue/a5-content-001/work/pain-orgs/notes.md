# pain-orgs notes (A5-CONTENT-001, 2026-11-14)

## Method
Sequential curl (browser UA) of each source site, its resource subpages and the YouTube/Vimeo channels/playlists they link to. YouTube: first page of channel `/videos` and playlist HTML (title, duration, relative age) plus oEmbed for linked ids. Vimeo: oEmbed (title, description, duration, upload date) for every id found on the Pain Toolkit pages and all 22 pages of vimeo.com/painbc/videos. WebSearch used only to locate channels or real sites for unverified sources. Recency rule applied (cutoff 2019-11-14; `recency_band` `<=5y` / `5-7y`; audio exempt).

## Counts
- Recorded assets: 354 (Pain Toolkit 64, Pain Revolution 2, Painaustralia 14, Pain BC 216, PRT Center 28, Flippin' Pain 23, Pain Canada 7).
- Excluded: 269 (75 outside_recency_window, 52 off_topic, 39 duplicate_listing, 38 off_scope, 21 not_reviewed_host_not_allowlisted, 16 age_unverified, 13 French twins, 10 platform duplicates, 5 unavailable).
- Rejected (requires_payment_or_login): 11 (10 PRT, 1 Pain Toolkit Academy).
- Reviewed with content (transcript/captions/viewing): 0. 38 records have a publisher-supplied description (Vimeo oEmbed or resource-page text); all others are title/duration/age only, so no summaries or classifications were made from titles.

## What could not be done and why
- YouTube watch pages are bot-gated (LOGIN_REQUIRED); not bypassed. No descriptions, chapters, caption info or exact dates for YouTube items.
- Paging past the first 30 channel videos would need YouTube's internal browse API; that call was refused by the permission system and not retried. Channel coverage is the newest 30 per channel.
- Hosts blocked (see issues in assets.json): michiganmedicine.org, medresearch.umich.edu, paincanada.ca, flippinpain.com.au, livewellwithpain.com.au/.co.uk, thechronicpainmethod.com(.au), soundcloud.com, simplecast (PRT podcast), spotify/apple/abc/sbs/tkex/bodylogic/nps.
- Michigan Medicine / Kratz Lab 'Animated Chronic Pain Coping Strategies': not found (searches returned only unrelated items and a 7y-old Michigan research-center video set). Nothing recorded.
- The Chronic Pain Method: real site is thechronicpainmethod.com.au (Willoughby NSW; physio+psychotherapy model, paid course/membership for practitioners per search snippets, not site-verified). A different "Dr Dawn Macintyre" YouTube channel appeared; NOT assumed to be the same person (spelling differs). Nothing recorded.

## Publisher identity (from own pages)
- Pain Toolkit: Pete Moore; attended INPUT Pain Management Programme 1996; Expert Patients Programme senior trainer for pain 2002-08; coach/adult-teaching City & Guilds. A patient-expert/educator, not a clinician. Katie Knapton is a physiotherapist (site). Terms: personal non-commercial viewing only.
- Pain Revolution: founder/CEO Lorimer Moseley, "Bradley Distinguished Professor in Clinical Neuroscience at Adelaide University"; Adelaide University initiative. Resources page curates external media ("independent of Pain Revolution"); it has no YouTube channel of its own that I could find.
- Painaustralia: "national peak pain advocacy body" since 2011; advocacy, not a clinical provider. Channel has a "Painaustralia Videos" playlist, mostly 10-14 years old.
- Pain BC: provincial pain organisation (BC, Canada); Pain Canada says it is "supported by Pain BC". Vimeo account vimeo.com/painbc holds LivePlanBe+ clips.
- PRT Center: Pain Reprocessing Therapy Center LLC; co-founders Paulina Soble LCSW and Daniella Deutsch LCSW; trainer Yoni K. Ashar PhD (Univ. Colorado). Claims recorded as publisher claims with their stated limits (disclaimer; FAQ says check with a medical provider first; "won't eliminate structural pain").

## register_updates
```json
[
 {"source_id":"SOURCE-017","disposition":"enumerated_partial","note":"Vimeo 2020 12-tool set (5-7y) kept; 2017 set excluded by recency; YouTube channel first page + 8 playlists enumerated; ~14 conference/webinar playlists not enumerated; SoundCloud podcast (10 eps) host blocked; Academy courses (Thinkific) rejected as paid. Publisher is Pete Moore (patient-expert, INPUT PMP 1996, EPP trainer 2002-08); site terms = personal non-commercial viewing."},
 {"source_id":"SOURCE-018","disposition":"enumerated","note":"No own channel; resources page lists 5 videos (2 kept: TEDxHobart Lauren Cannell 3y, Comcare 'Pain revolution' talk 4y; 3 older excluded) and 9 podcasts (hosts blocked) and books/sites (excluded). Founder Lorimer Moseley verified on team page."},
 {"source_id":"SOURCE-019","disposition":"enumerated_partial","note":"Channel first page + Brainman, Painaustralia Videos and SCS playlists enumerated; 14 kept (Pain Journeys x8, Wear it Red x4, My Pain Story, consumer forum); most education items 10-14y old (excluded) or age unverified; SCS/policy excluded as off-scope. Advocacy body."},
 {"source_id":"SOURCE-021","disposition":"enumerated_partial","note":"216 kept: @Home Gentle Movement/Hand Drumming series (37+2 sessions, 6y), Trades and Pain tips, support/peer-support clips, Spoon Theory webinar, ~170 Vimeo LivePlanBe+ clips 2021-2023 (some French). Provider webinars excluded. YouTube channel only first 30 newest; 14 Vimeo ids oEmbed-empty."},
 {"source_id":"SOURCE-022","disposition":"enumerated","note":"All free items (webinars, meditations, somatic tracking, research roundup, fibromyalgia webinar) require LearnWorlds free-account login: 10 rejected requires_payment_or_login; Healing Workshop paid. 16 podcast episodes recorded as discovered from page text (simplecast host not allowlisted). 2 third-party news videos kept with PRT cautions. Claims recorded as information, not routed."},
 {"source_id":"NEW-FlippinPain","disposition":"enumerated_partial","note":"Site www.flippinpain.com.au 502 on retry, bare domain 403. YouTube @flippinpain (channel About: UK public health movement, science of pain) first page: 23 kept (public 'Do you get it?' events, arthritis/fibromyalgia events, short films), 7 excluded promo. Identity not verified from site."},
 {"source_id":"NEW-PainCanada","disposition":"blocked_partial","note":"paincanada.ca 403. YouTube @paincanada (About: national initiative supported by Pain BC) first page: 7 EN conference sessions kept (title-only), FR twins/policy/flare-plan sessions excluded. 11+ conference playlists not enumerated."},
 {"source_id":"NEW-LiveWellWithPain","disposition":"unresolved","note":"livewellwithpain.com.au 502/403; web search indicates the real programme is UK (livewellwithpain.co.uk, 403). Only a third-party clinician presentation (HealthInnoWest Vimeo 1031868464, 2024, 'Putting Live Well with Pain') found; not recorded as source media. Needs hosts allowed."},
 {"source_id":"NEW-ChronicPainMethod","disposition":"unresolved","note":"thechronicpainmethod.com fails (protocol error); real site thechronicpainmethod.com.au (403). Search indicates practitioner course/membership (likely paid). No media recorded."},
 {"source_id":"NEW-MichiganMedicine-Kratz","disposition":"not_found","note":"Hosts michiganmedicine.org/medresearch.umich.edu 403; video 'Animated Chronic Pain Coping Strategies' not found via YouTube search. No media recorded."}
]
```

## Recommendations
1. Allow: thechronicpainmethod.com.au, livewellwithpain.co.uk (and .com.au), paincanada.ca, flippinpain.com.au, medresearch.umich.edu, michiganmedicine.org, soundcloud.com, the PRT simplecast host, and podcast hosts used by Pain Revolution if audio is wanted.
2. Decide whether a YouTube data route (official Data API key or captions access) is acceptable; without it YouTube items stay title-only.
3. Pain BC's Vimeo LPB+ clips are the richest free no-login set but need caption/transcript review to classify; consider keeping only English.
4. Decide on borderline kept items: Pain Revolution/Comcare talk, Painaustralia consumer forum, Pain Canada conference sessions, Pain Toolkit "In Conversation" episodes (all title-only).
