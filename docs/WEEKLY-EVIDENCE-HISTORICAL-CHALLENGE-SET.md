# Historical challenge set — DRAFT, needs human verification before use as evaluation evidence

Built 2026-11-23 from read-only public web research (approved by the Captain), by three research workers, using Firecrawl search/scrape.
Nothing was fabricated by design: entries without a verifiable verbatim headline or a second source were dropped, and the reasons are in each
file's `dropped` list. Files: `tests/fixtures/historical_challenge_{au,intl,negatives}.json`.

## Coverage
| Part | Entries | Detail |
|---|---|---|
| Australia, incidents | 12 | telecom 3 (Optus 2023 outage, Optus 2022 breach, Optus 2025 triple-zero failure), cyber/breach 5 (Medibank, Latitude, Qantas, MediSecure, DP World ports), energy 1 (AEMO market suspension June 2022), banking/payments 2, aviation 1 (Airservices Nov 2025) |
| International, incidents | 12 | CrowdStrike/Windows, AWS us-east-1, Cloudflare Nov 2025, Google Cloud June 2025, Log4Shell, Kaseya, Colonial Pipeline, Change Healthcare, M&S, JLR, Heathrow substation fire, Iberian blackout |
| Negatives | 15 | false alarms 5, routine notices 4, retrospective/commentary 4, **misleading headlines 2 (target was ≥4)** |
Event types across the 24 incidents: outage 10, cyber incident 6, data breach 5, physical 2, vulnerability 1. Australian entries: 12 incidents plus 6 of the 15
negatives.

## Known weaknesses (each is also recorded per entry in `verification_notes`)
* **Sources.** Four incidents have no official source (Latitude 2023, the 2021 multi-bank outage, CBA June 2023, Airservices 2025); they rest on two
  mainstream sources. Four source rows have no publication date (left null, not guessed).
* **Headlines are not guaranteed verbatim.** Many were read from search-result excerpts or page metadata rather than the rendered page; several pages show
  differing tab title, og:title and h1; some Reuters slugs differ from the live headline. A human must confirm each headline against the page before
  it is used as a test input.
* **`first_credible_report_headline` is the earliest headline the workers could verify, not provably the earliest published.** The Colonial Pipeline official
  source is a 2023 retrospective, and the Change Healthcare onset date comes from secondary sources.
* **Several negatives are real, large outages** (Cloudflare Nov 2025, Iberian blackout, a US FAA notice outage, Facebook 2021, CrowdStrike) that are negatives only
  for "cyberattack/breach" classification; each says so, and they must not be scored as non-incidents for outage detection.
* Candidates not researched: SolarWinds, MOVEit, Azure/365, Cloudflare Dec 2025, Texas winter storm, ProxyShell/Citrix/Ivanti; Australian Sydney Trains/Metro,
  retail and Services Australia incidents.
* The set is Australia-weighted only partly; the negative set is mostly international.

## Use
Not yet scored. After human verification, run the frozen model once as a separate stratum: report recall on the 24 known-critical incidents (does a serious
single-source first report reach ESCALATE or at least VERIFY?) and false-alarm rate on the negatives, with exact intervals. n=24 incidents cannot support a
release threshold; it is a challenge test, not an estimate of production performance.
