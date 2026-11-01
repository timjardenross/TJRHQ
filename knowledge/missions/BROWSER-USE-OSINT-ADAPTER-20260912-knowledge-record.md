# Knowledge Record — Browser Use OSINT adapter, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | none (net-new capability, not in the 2026-08-23 audit) |
| Title | A hard-pinned dependency required isolating a whole venv, and the recommended PoC source turned out unreachable from this host |
| Date | 2026-09-12 |
| Lesson | LL-149 |

## Outcome

Added `intelligence/ingestion/browser_adapter.py` — a headless-browser
ingestion adapter for sources with no RSS/API and no working plain-HTTP
scrape path (JS-rendered pages, or servers that time out on a bare
`urllib` fetch). Subclasses `ScrapeAdapter` and overrides only
`_fetch_html()` — all extraction (CSS-selector lists, status-narrative,
link fallback), content validation, and health reporting is inherited
unchanged via `BaseSourceAdapter.run()`. Wired into
`collection_engine.py`'s `_ADAPTER_MAP` under `source_type="browser"` —
only ever selected for a source explicitly registered that way, never a
silent second collection path for a source with a working rss/api/scrape
path already (would duplicate collection and skew
`source_fidelity_report()`'s signal-to-noise metrics).

Two real problems surfaced during implementation, both fixed:

1. **`pip install browser-use` into the shared `platform-runtime/.venv`
   silently downgraded production dependencies.** `browser-use` hard-pins
   (`==`, not `>=`) exact versions of `anthropic`, `google-genai`, `mcp`,
   `google-api-core`, `google-auth` — a straight `pip install` into the
   venv every other service in this platform shares dropped
   `google-genai` from 2.19.0 to 1.65.0 and `anthropic` from 1.0.0 to
   0.76.0, the exact SDK versions `core/platform/memory_graph.py`
   (Graphiti) and `core/platform/unified_memory.py` (mem0) — both wired
   earlier the same day — depend on. Caught immediately (before any commit
   used the broken state), reverted, and re-verified both Task 1's
   RELATIONSHIPS recall and `tools/test_mem0.py` still passed on the
   restored versions. Fixed properly by giving the browser worker its own
   isolated venv (`intelligence/ingestion/browser_worker/.venv`, not
   tracked in git, `pip install`ed per the worker's own
   `requirements.txt`) invoked via `subprocess.run()` from
   `browser_adapter.py` — zero shared dependency surface with
   `platform-runtime/.venv`.
2. **`browser-use`'s CDP-based navigation needed real debugging past two
   library-level rough edges** before it worked at all: `page.evaluate()`
   requires its argument to be a JS arrow-function string
   (`"() => ..."`), not a bare expression (fails with a confusing "must
   start with (...args) =>" error otherwise); and `page.goto()` only
   fires the CDP `Page.navigate` command and returns immediately — it does
   **not** wait for the page to actually load, so an `evaluate()`
   immediately afterward hits `document.documentElement is null` (still on
   `about:blank`). Fixed by polling `document.readyState` in a loop up to
   the timeout budget before extracting HTML.

**The audit-recommended PoC source (NEMA, nema.gov.au) turned out
unreachable from this deployment VM entirely** — confirmed via plain
`curl` (times out, `ERR_HTTP2_PROTOCOL_ERROR`/connection timeout) and via
direct headless Chrome (`--dump-dom`, same result, with and without
`--disable-http2`) — not a headless-browser-specific problem a better
fetch method could route around. The other two candidates flagged in the
same investigation (CISC, eSafety Commissioner) were checked too and are
also unreachable from this host right now. `source_type` for NEMA was set
to `"browser"` (correct, ready) but `active` was left `False` with an
honest note — activating a permanently-unreachable source would just
generate constant `"failed"` health checks, worse than leaving it
inactive. **The adapter mechanism itself was proven fully end-to-end
against a different, genuinely reachable, genuinely JS-rendered site**
(`https://quotes.toscrape.com/js/` — content only exists after JS
execution, a real test of exactly the capability this adapter exists for)
— confirmed via `intelligence/ingestion/browser_worker/fetch_html.py` run
standalone, returning the real rendered `<div class="quote">` markup.

## Lesson

A library that wraps another tool (browser-use wraps Playwright/CDP) can
still bring its own hard dependency graph, and that graph is invisible
until you actually run `pip install` — the task's own instruction to
"confirm which Chromium build it needs... before installing a second one"
correctly anticipated the *browser binary* question but not the *Python
package* question, which turned out to be the actually dangerous one here.
Anything installed into a shared venv should be assumed to have this risk
until checked, especially late in a multi-task session where earlier tasks
already made that venv load-bearing for something new.

Separately: an audit or task-brief's specific example ("use this source as
your PoC") is a suggestion informed by evidence gathered at some earlier
point, not a guarantee the example still holds — network reachability from
a specific host is exactly the kind of fact that can change (or never have
been true from *this* host) without anyone noticing until someone actually
tries it.

## Future Guidance

Before installing any new pip package into `platform-runtime/.venv`
specifically (the platform's one shared, load-bearing venv), check its
declared dependencies for pinned (`==`) versions of anything already used
elsewhere in the platform (`anthropic`, `google-genai`, `openai`,
`mistralai` are the ones that matter most here, per today's session alone)
before running the install — a `pip download --no-deps` or reading the
package's own metadata first is cheap; reverting a silent platform-wide
downgrade after the fact is not guaranteed to be caught immediately by
whoever hits it next.
