# HQ Evolution — Expanding External Research Sources (research / proposal)

Status: **Phase 1 + 2 + 3 fully implemented** (2026-09-25/26) — topic
rotation, the `sort=updated` fix, `dependency_releases` (Phase 1); the
`sources/` adapter registry, arXiv/HN/HF adapters, `queries` schema,
per-source caps, per-source enrichment fetchers (Phase 2); the MCP
registry adapter, deps.dev/Scorecard/Semantic Scholar supply-chain
evidence enrichment, vendor-changelog reuse, and the budget-capped
Firecrawl paid-search source (Phase 3) are all live in
`scripts/self_improvement/`. See §11/§12 for how the paid-search gating
condition was actually resolved, and §12 for which of the 9 watchlist
topics now use which sources.
Date: 2026-09-26
Scope: `scripts/self_improvement/external_discovery.py`, `external_enrichment.py`,
`config/evolution_watchlist.json`, the `evolution` block of
`config/self_improvement_policy.json`.

## 1. Where we are today

The nightly HQ Evolution cycle (`deploy/hq-evolution.timer`, 03:00) has exactly
one external source: GitHub repository search.

| Stage | Today | Limitation |
|---|---|---|
| Discovery | `external_discovery.discover()` → `GET api.github.com/search/repositories?q=<github_query>&sort=updated` per watchlist topic | Only finds *repos*. Papers, model releases, vendor features, release notes of tools HQ already runs, and practitioner write-ups are invisible. |
| Topic coverage | `watchlist_topics[:max_external_searches_per_cycle]` with the bound at **6** and **9** topics in the watchlist | Topics 7–9 (`mcp-integrations`, `task-decomposition`, `local-inference`) are only ever searched on nights when an earlier topic has resolved in `state_validation.py`. In practice they are mostly never researched. |
| Ranking inside a search | `sort=updated` | Favours whatever was pushed most recently (often forks/toy repos), not quality. |
| `value` signal | `stargazers_count >= 500` | Stars are the only value signal, and are GitHub-specific. |
| Enrichment | `external_enrichment.enrich()` fetches the **GitHub README** of the top 3 | `_repo_full_name_from_source()` returns `None` for any non-GitHub URL, so any new source type gets no enrichment. |

What is already sound and should **not** change: the research order
(internal validation → external discovery), the `why_relevant` requirement,
the deterministic `RelevanceGate`, fingerprint + near-duplicate dedup, and
fail-open behaviour on network errors. A wider source base should feed the
**same** gate. It should not add a second path around it.

## 2. Candidate sources, ranked by fit for HQ

The criteria are: no auth or a free key, a stable JSON/Atom API, a clear
mapping to the existing candidate shape, and a real tie to an HQ gap. This
rules out generic trend scanning (spec section 8).

### Tier 1 — highest signal, lowest effort

| Source | API | Answers | Maps to topics | Notes |
|---|---|---|---|---|
| **Release notes of dependencies HQ already runs** | PyPI JSON (`pypi.org/pypi/<pkg>/json`), npm registry (`registry.npmjs.org/<pkg>`), GitHub Releases (`/repos/{o}/{r}/releases`) | "What became possible in things we already use?" (new features, deprecations, breaking changes) | All of them. Especially `retrieval-evaluation` (deepeval, ragas), `observability-llm-ops` (Phoenix), model SDKs, Supabase, Next.js | **Best fit of any source.** Relevance is built in because HQ already depends on the package. Build the list from the existing `requirements*.txt` (16 files, excluding vendored `.venv` copies) and `lcars-portal/package.json`. Don't maintain a second hand-written list. PyPI and npm both returned 200 from the sandbox. |
| **arXiv** | `export.arxiv.org/api/query` (Atom, no key, ≤1 req / 3 s) | Techniques that don't exist as repos yet | `long-term-memory`, `retrieval-evaluation`, `model-routing`, `task-decomposition` | A paper is a *concept*, not an adoptable component. Use lower default `evidence_strength` (see §4). |
| **Hacker News (Algolia)** | `hn.algolia.com/api/v1/search?tags=story&numericFilters=points>50` | Practitioner signal: what engineers are actually adopting or complaining about | All, especially `local-inference`, `observability-llm-ops` | The points threshold is the noise filter. The story URL often points to a GitHub repo, so dedup against the GitHub candidate should use the canonical repo URL. |
| **Hugging Face Hub** | `huggingface.co/api/models?search=…&sort=downloads` (no key for reads) | New or quantised models that could replace a paid route | `local-inference`, `model-routing` | Directly feeds the "move a `TASK_POLICY` cloud route local" question. Downloads and likes act as the `value` signal. |

### Tier 2 — worthwhile, moderate effort

| Source | API | Use | Notes |
|---|---|---|---|
| **MCP server registry** | `registry.modelcontextprotocol.io` (official) and npm search `registry.npmjs.org/-/v1/search?text=mcp server` | `mcp-integrations` topic | Much better targeted than GitHub `topic:mcp`. npm search returned 200 from the sandbox. |
| **Vendor changelogs / engineering blogs (RSS)** | Existing `intelligence/ingestion/rss_adapter.py` | Model-provider, Supabase, Vercel, Next.js feature launches | **Reuse, don't rebuild.** The intelligence source registry already has 34 `cloud_technology` sources, mostly status pages. Tag a small subset as HQ-Evolution-relevant, or read their already-ingested signals, rather than adding a second fetcher. Per AGENTS.md "check-first registries", grep `SOURCES` in `tools/intelligence/seed_source_registry.py` before adding any feed. |
| **Semantic Scholar** | `api.semanticscholar.org/graph/v1/paper/search` (unauthenticated, low rate limit; free key raises it) | Citation count as the `value` signal for arXiv candidates | Enrichment, not discovery. |
| **deps.dev + OpenSSF Scorecard** | `api.deps.dev/v3/...`, `api.securityscorecards.dev/projects/github.com/{o}/{r}` | Supply-chain evidence for section 41 (maintenance, dependency count, security practices) | Enrichment, not discovery. Replaces the current licence/archived-only `complexity` heuristic with real evidence. |

### Tier 3 — not recommended now

| Source | Why not |
|---|---|
| Reddit | API needs OAuth plus agreement to commercial API terms (since 2023). HN covers most of the same practitioner signal. `intelligence/classification/source_tier.py` already classes reddit.com as low-tier. |
| X / Twitter | Paid API, high noise. |
| Papers with Code | Sunset in 2025 (redirects to Hugging Face). Use HF + arXiv instead. |
| Paid web-search APIs (Brave, Tavily, Exa, Firecrawl search) | Possible later, but only behind the existing `intelligence/ingestion/external_fetch_budget.py` hard-cap circuit breaker, and only once the free sources above are shown to leave gaps. |
| OSV.dev / GitHub Advisory DB for vulnerability discovery | `.github/dependabot.yml` already covers this. Adding it would duplicate a working pipeline. |

## 3. Proposed architecture change

Keep everything downstream of discovery unchanged. Turn discovery into a small
adapter registry.

```
config/evolution_watchlist.json  (per topic)
  "queries": {
     "github":  "local llm model router topic:llm-router",
     "arxiv":   "ti:\"LLM routing\" OR abs:\"model cascade\"",
     "hn":      "llm router",
     "hf":      "router"
  }
  # "github_query" stays accepted as an alias for queries.github (backwards compatible)

scripts/self_improvement/sources/          (new, one module per source)
  github.py   arxiv.py   hn.py   hf.py   dependency_releases.py
  each: search(query, limit, timeout) -> list[candidate]   # same dict shape as today

external_discovery.discover()
  for topic in rotated(topics):            # see §5
    for source, query in topic.queries:    # bounded per source
      candidates += SOURCES[source].search(...)
```

Each adapter must:

- Return the **same candidate dict** `_repo_to_candidate()` builds today, with
  `provenance[0].source` set to the adapter name (`"arxiv"`, `"hn"`, …) and
  `source` set to a canonical URL, so `new_fingerprint()` and
  `find_near_duplicate()` work unchanged.
- Fail open the same way `_get_json()` does: a network error means no
  candidates from this source this cycle, never a failed cycle.
- Set its own honest `value` / `evidence_strength` / `complexity` (§4). It must
  not reuse GitHub-star logic.

Enrichment (`external_enrichment.py`) needs one change: a per-source content
fetcher. That is the README for GitHub, the abstract for arXiv (already in the
Atom response, so no extra call), the linked URL's title and top comment for
HN, and the model card for HF. Without it, non-GitHub candidates are always
scored on discovery-stage constants.

`relevance.py` does not change.

## 4. Scoring inputs per source

`RelevanceGate.score_candidate()` weighs fit 0.35, value 0.35 and evidence
0.30, minus a complexity penalty. Each adapter should map its native signals
onto those fields explicitly:

| Source | `value` from | default `evidence_strength` | `complexity` from | `change_class` |
|---|---|---|---|---|
| GitHub | stars (as today) | moderate | licence / archived (as today, later Scorecard) | topic class |
| Dependency release | always `high` (already a dependency) | strong (vendor's own release notes) | `low` for minor, `moderate` for major-version bumps | topic class, or `reliability` for deprecations |
| arXiv | citations via Semantic Scholar, else `low` | weak (a claim, not a proven implementation) | `high` (no implementation to adopt) | topic class |
| HN | points (≥200 → medium, ≥500 → high) | weak | inherit from the linked repo if there is one | topic class |
| HF | downloads / likes | moderate | licence (many model licences restrict use) | `cost_optimisation` for `local-inference` |

With these defaults, papers and HN threads rarely clear
`min_relevance_score_to_surface` (0.65) on their own. That is intended: they
should mostly reach the Captain *after* enrichment has confirmed fit, or as
corroborating provenance on a GitHub or dependency candidate for the same
concept.

## 5. Budget changes

The spec's funnel is "DISCOVER MANY → relevance filter → dedup → shortlist →
deep investigation of FEW". Widening discovery is cheap because the gate and
dedup are deterministic. The paid part (LLM enrichment and investigation) can
stay bounded exactly as it is.

| Setting | Today | Proposed | Why |
|---|---|---|---|
| Topic selection | first N topics | **rotate**: sort topics by last-searched timestamp, take the N stalest | Every topic gets researched at least every ~2 nights, instead of topics 7–9 almost never |
| `max_external_searches_per_cycle` | 6 | 20 (with per-source caps below) | Counts topic × source searches, not topics |
| per-source cap (new) | — | github 6, arxiv 4, hn 4, hf 3, dependency_releases 1 batch | arXiv rate limit is 1 req/3 s, so 4 searches ≈ 12 s |
| `max_external_candidates_per_cycle` | 20 | 40 | More raw candidates; the gate discards most |
| `max_external_enrichments_per_cycle` | 3 | 5 | Only LLM-cost line that grows |
| `max_shortlist_per_cycle` / `max_investigations_per_cycle` / `max_opportunities_surfaced_per_cycle` | 6 / 6 / 3 | unchanged | Captain-facing output volume stays the same; it just gets better candidates |
| `run_duration_budget_minutes` | 20 | unchanged | ~20 extra HTTP calls at 8 s timeout fit comfortably |

Also switch GitHub search from `sort=updated` to default best-match plus a
`pushed:>` date qualifier. That keeps results recent without ranking by
"whoever pushed last".

## 6. Suggested new watchlist topics

Every new topic still needs a `gap_hypothesis`, a `why_relevant` and, where
possible, a deterministic `validation` block. These are candidates for that
work, not ready-made entries:

- **Prompt-injection / tool-use safety for MCP and agents.** HQ integrates
  several MCP servers and has an adversarial-review history
  (`docs/security/2026-09-15-adversarial-review-remediation.md`). Sources:
  arXiv, HN, GitHub.
- **Prompt caching / token cost reduction.** This ties directly to the
  Model Router's paid routes. Sources: dependency releases (provider SDKs),
  vendor changelogs.
- **Agent / LLM-output evaluation beyond hallucination.** This extends the
  `retrieval-evaluation` topic now that `score_output()` exists.

## 7. Rollout plan

1. **Phase 1 (small, no new network hosts beyond ones already in use).**
   - Topic rotation.
   - `sort=updated` fix.
   - `dependency_releases` adapter over PyPI, npm and GitHub Releases for
     packages parsed from existing manifests.
2. **Phase 2.**
   - `queries` schema with `github_query` alias.
   - arXiv, HN and HF adapters.
   - Per-source scoring defaults.
   - Per-source enrichment fetchers.
   - Tests in the style of `tests/test_external_enrichment.py`, using
     recorded fixtures with no live network.
3. **Phase 3.**
   - MCP registry adapter.
   - Scorecard / deps.dev / Semantic Scholar enrichment.
   - Read HQ-Evolution-tagged vendor-changelog signals from the intelligence
     pipeline.
   - Only then consider a budget-capped paid search API.

## 8. Open questions / prerequisites

- **Egress allowlist on the production host.** From the Claude Code sandbox
  only `pypi.org` and `registry.npmjs.org` were reachable. arXiv, HN Algolia,
  Hugging Face, deps.dev, Scorecard, Semantic Scholar and OSV were all refused
  by *this sandbox's* egress proxy. The production VM has a different
  allowlist; `HQ-EVOLUTION.md` already notes the same sandbox-vs-production
  difference for GitHub. Confirm each host from `/opt/starship-endeavour`
  before building its adapter.
- **GitHub rate limit.** Unauthenticated search allows 10 req/min, and the
  REST API allows 60 req/hour. Six searches plus three README fetches fit
  today. Twenty-plus release lookups do not, so Phase 1 needs either a
  read-only token or PyPI/npm as the primary release source with GitHub
  Releases as a fallback.
- **Per-source attribution in the portal.** The self-improvement findings
  UI should show `provenance.source` so the Captain can see where a
  candidate came from. It is already stored, but check whether it is
  rendered.

## 9. Validation notes (2026-09-25 code review)

Checked this doc's claims against `/opt/starship-endeavour` at PR time. All
of §1's numbers are live, not aspirational: `sort=updated` at
`external_discovery.py:128`, the `stargazers_count >= 500` threshold at
`external_discovery.py:80`, the 0.35/0.35/0.30 weights at
`relevance.py:59`, and every budget number in §5's "Today" column matches
`config/self_improvement_policy.json` exactly (6 / 20 / 3 / 0.65 / 20 min).
The topic-starvation claim is real: 9 topics exist in
`config/evolution_watchlist.json`, `max_external_searches_per_cycle` is 6,
and `watchlist_topics[:max_searches]` is a plain list slice with no
rotation logic anywhere in the codebase — topics 7–9 are simply never
reached. `.github/dependabot.yml` exists (Tier 3 rejection is justified),
`intelligence/classification/source_tier.py` does list `reddit.com` as
low-tier, and `intelligence/ingestion/rss_adapter.py` exists (reuse claim
is valid). The dedup reasoning in §2's HN row also checks out:
`new_fingerprint()` hashes `discovery_source:source:title`
(`opportunity_store.py:78-88`), so an HN adapter only collapses onto a
GitHub candidate if it sets `source` to the resolved GitHub URL rather
than the HN thread URL, exactly as the doc specifies.

Two follow-ups this review surfaced, not yet folded into the plan above:

- **Rotation (§5) needs a `last_searched` timestamp added to each of the 9
  existing watchlist topics.** No such field exists today, so "sort by
  last-searched, take the N stalest" has nothing to sort by on first run.
  Add this as an explicit Phase 1 migration step, and decide whether a
  fail-open (network error) counts as "searched" for rotation purposes —
  currently ambiguous.
- **Gate Phase 2 explicitly on the §8 egress spike, not just "confirm each
  host."** Reachability for arXiv, HN Algolia and Hugging Face from the
  production host is unverified (only `pypi.org` and
  `registry.npmjs.org` responded from the sandbox). Recommend making this
  a literal go/no-go check before Phase 2 work starts, rather than a
  footnote resolved implicitly during implementation.

## 10. Phase 2 implementation notes (2026-09-26)

Egress spike run for real from the production host (`/opt/starship-endeavour`,
not the sandbox): arXiv, HN Algolia, Hugging Face, deps.dev, OpenSSF
Scorecard, Semantic Scholar, and the MCP registry are all reachable — none
of the sandbox's restrictions apply here. Gate cleared; built the `sources/`
adapter registry (`github.py`/`arxiv.py`/`hn.py`/`hf.py`/`common.py`), the
`queries` schema with the `github_query` alias, `per_source_search_caps`,
and per-source enrichment content fetchers (README / stored abstract / HN
top comment / HF model card).

**arXiv finding, corrected from an earlier session's note in this PR
thread:** the first pass concluded arXiv's edge WAF rejected literal `"` in
the query string. Systematic retesting disproved that — the actual cause is
that arXiv's export API is currently returning HTTP 406 for **every fresh
(cache-MISS) query regardless of content** (`all:electron`, a heavily-cached
query, returns 200 from Fastly's cache; `all:model`, `ti:routing`, and even
an unused nonsense term all 406 as cache-MISSes going to origin). This looks
like a transient degradation on arXiv's side as of 2026-09-25/26, not a
content-based block. `arxiv.py`'s `_sanitize_query()` (rewriting a quoted
phrase into an AND of its words) is kept regardless, since it's a reasonable
defensive measure and does no harm — but it was not the fix. The adapter's
existing fail-open contract already covers this correctly: a 406/network
failure logs a warning and returns `[]`, same as any other source outage,
so arXiv candidates will simply resume once arXiv's API recovers with no
further code change needed. HN and HF were live-verified end-to-end from
this host and returned real, correctly-shaped candidates.

## 11. Phase 3 implementation notes (2026-09-26)

Built: `sources/mcp_registry.py` (official registry.modelcontextprotocol.io,
live-verified — an entry with no linked GitHub repo is skipped, since
there's nothing for an integration decision to evaluate), `sources/
vendor_changelog.py` (reads the existing `intelligence_events` table for
`category='cloud_technology'` rather than adding a second RSS fetcher, per
§2's "reuse, don't rebuild" — degrades to no candidates when
`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` aren't set, same fail-open
contract as every other source), and `sources/deps_dev.py` +
`sources/scorecard.py` + `sources/semantic_scholar.py` (enrichment, not
discovery — `external_enrichment.apply_supply_chain_evidence()`, called
before the LLM-ranked enrichment pass so ranking itself sees the sharpened
fields). deps.dev's own project response already embeds an OpenSSF
Scorecard result for most GitHub-hosted repos (`scorecard.overallScore`,
live-verified against `psf/requests`: 8.2), so `scorecard.py`'s dedicated
API call only fires as a fallback when deps.dev has no embedded score —
avoids doubling the request count for the common case. Both were
live-verified from this host.

**The budget-capped paid search API (§2 Tier 2, deliberately last in §7's
rollout) IS now built** (`sources/firecrawl_search.py`, 2026-09-26,
Captain-directed follow-up). What actually unblocked it wasn't a new
evidence-of-gap finding — it was that the "provider decision" this
document flagged as a blocker turned out to already be made: Firecrawl is
a provisioned, budget-gated fetch path this repo already runs in
production (`intelligence/ingestion/firecrawl_client.py`,
`intelligence/ingestion/external_fetch_budget.py`, provider="firecrawl"),
not a new vendor/key to source. The adapter shares that SAME real
account-wide monthly cap with the intelligence pipeline's existing usage
— deliberately, not a separate budget that could double real spend — and
degrades to no candidates on any refusal, same fail-open contract as
every other source.

The evidence-of-gap concern this section originally raised is handled by
scope instead of by proof: `per_source_search_caps.firecrawl_search`
defaults to 1 search/cycle, and — unlike every other source — no
watchlist topic enables it by default. It only ever fires for a topic
whose `queries` dict explicitly adds a `"firecrawl_search"` key, so it
stays genuinely last-resort until a specific topic is deliberately opted
in. NOT live-tested against the real API during development — doing so
would spend a real credit from the Captain's shared account for no
operational reason; built and unit-tested against Firecrawl's documented
`/v1/search` response shape instead.

## 12. Two follow-up items closed (2026-09-26)

**Per-source attribution in the portal (§8's open question) — already
handled, no code change needed.** Checked
`lcars-portal/src/app/self-improvement-findings/_components/OpportunityDetail.tsx`:
every candidate's `provenance` array is already rendered, both as a
compact joined summary line and in a full "Evidence & provenance"
expandable section showing each entry's `source`/`location`/`detail`
verbatim. It has no hardcoded source-name switch, so every new source
this doc has added (arxiv/hn/huggingface/mcp_registry/vendor_changelog/
dependency_release/firecrawl_search) renders correctly with zero
frontend change. The concern raised in the first review was
speculative, not confirmed — now confirmed false.

**A few watchlist topics now actually use the new sources.** Every
adapter built in Phase 2/3 existed but sat dormant — no topic's `queries`
dict referenced anything but `github`. Wired four of the 9 topics in
`config/evolution_watchlist.json` to the sources that most directly match
their own `why_relevant`: `model-routing` (+ arxiv, hn), `retrieval-evaluation`
(+ arxiv), `mcp-integrations` (+ mcp_registry), `local-inference` (+ hf,
hn). The arXiv queries use bare AND-joined terms (`ti:LLM AND ti:routing`),
not quoted phrases, per §10's finding. The other 5 topics and
`firecrawl_search` were deliberately left untouched — narrower blast
radius, and firecrawl_search specifically should stay opt-in per §11.

## 13. Real cycle run findings (2026-09-26) — `max_external_enrichments_per_cycle` reverted 5->3

Ran the real (non-dry) cycle twice against `/opt/starship-endeavour`
after merging Phase 1-3 + the followups. Confirmed working: 38 external
candidates found across sources in one cycle (not just GitHub —
real Hugging Face candidates surfaced via `local-inference`'s `hf` query,
e.g. `RedHatAI/Qwen3.5-9B-quantized`), and the highest-value opportunity
was a real `dependency_releases.py` find (`openai 3.13.0 -> 3.19.2`).
arXiv still 406s (§10, unresolved on their end) and deps.dev/Scorecard
404 for several small/new repos — both failed open exactly as designed,
no crash.

**Real regression found and fixed**: `hq-evolution-external-fit`
(external_enrichment.py's LLM call, routed to Gemini cloud via
`core/model-router/app.py`'s TASK_POLICY, `timeout: 400`) took 4-5.5
minutes per call in both live runs — pre-existing, already-tuned cloud
latency (git history shows this timeout was already bumped 300->400s
before this doc existed), not something this doc's changes caused
directly. But Phase 2 bumped `max_external_enrichments_per_cycle` from
3 to 5 without checking that assumption against this route's real
latency: 5 sequential calls at ~4-5min each burned the entire
`run_duration_budget_minutes` (1200s) before the SHORTLIST/INVESTIGATE
phase ever started, so the cycle's own budget guard correctly fired
("Run duration budget (1200s) exceeded — stopping investigation early")
and produced `deep_investigated_count: 0`, `worth_considering_count: 0`
— a clean, non-crashing failure mode, but a wasted cycle. Reverted to 3.
Root-causing why this specific route is so slow (switching provider/model
for this task type) is a separate, bigger decision — not made here.
