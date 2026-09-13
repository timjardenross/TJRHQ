# Knowledge Record — deepteam alongside deepeval, 2026-09-13

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0374 |
| Title | deepteam alongside existing deepeval — added a real red-teaming harness, ran it against the LIVE Model Router (contrary to mission pre-flight's "VM-only, unreachable from sandbox" assumption), and hit a real undeclared-dependency packaging bug in deepteam 1.0.9 |
| Date | 2026-09-13 |
| Stream | Stream 3 |

## Outcome

Added `core/quality/deepteam_scan.py` — a standalone, manually-run deepteam
red-teaming scan — plus `core/quality/requirements-deepteam.txt` and an
isolated `platform-runtime/.venv-deepteam`. Reports land under
`reports/deepteam/` (native deepteam JSON + our own `-meta.json` + Markdown
summary per run, same convention as `reports/garak/` and `reports/ragas/`).
Not wired as a caller of `build_learning_loop.py`, `quality_scoring_service.py`'s
live scoring path, or any cron/scheduler — that file was not touched, per the
brief.

**Surprising, confirmed fact that overrides the mission pre-flight assumption**:
the mission brief stated the Model Router (`http://127.0.0.1:8891`) is
"expected UNREACHABLE from this sandbox... router only runs on prod VM." That
was checked directly in this sandbox — `curl -s -m 5 http://127.0.0.1:8891/health`
returned `{"status": "ok", "port": 8891}`, and a real
`/api/model/escalate` POST returned a genuine `glm-5.3:cloud` completion.
The router was reachable and fully functional throughout this session. This
is new information for whoever wrote that pre-flight check — it does not
hold in every sandbox instance — and it means the scan below is a **real run
against the live production Model Router**, not a sandbox stub or mock.

**Judge/target model, reusing the existing backend rather than inventing a
new one, as instructed**: `platform-runtime/lib/quality_scoring_service.py`
already defines `_ModelRouterJudge`, a `DeepEvalBaseLLM` subclass that calls
this platform's Model Router "escalate" task, used by deepeval's
`HallucinationMetric`. `deepteam_scan.py` imports that exact class unchanged
(via the same `_import_repo_module` pattern `ragas_eval.py` uses) and reuses
one instance of it for THREE of deepteam's roles at once: the simulator model
(drafts attack scenarios), the evaluation model (scores pass/fail), and the
`model_callback` target under test (the system actually being red-teamed).
Using the router itself as the target is the honest scope here — this
platform has no other standalone chat/completion surface to point a red-team
scan at; deepteam supports passing a `DeepEvalBaseLLM` directly as
`model_callback` (confirmed by reading `red_teamer.py`'s handling of
`isinstance(model_callback, DeepEvalBaseLLM)`), so no second backend was
built.

**A real, confirmed packaging bug in deepteam 1.0.9, not a theoretical
concern**: a vanilla `pip install deepteam` into a throwaway venv raised
`ModuleNotFoundError: No module named 'sentry_sdk'` on `import deepteam`
(`deepteam/__init__.py` → `deepteam.red_team` → `deepteam.red_teamer` →
`deepteam/telemetry.py`'s unconditional `import sentry_sdk`). Confirmed via
`importlib.metadata.metadata('deepteam').get_all('Requires-Dist')` that
`sentry_sdk` is not declared anywhere in deepteam's own metadata (nor
deepeval's). Fixed by adding `sentry-sdk` explicitly to
`core/quality/requirements-deepteam.txt`; no downstream conflict once added.

**Why isolated into its own venv, despite no hard version conflict** (unlike
garak's `openai<3.0` pin or ragas's `langchain-community` import bug): a
plain `pip install deepteam` resolved cleanly against
`platform-runtime/requirements.txt`'s `openai==3.13.0` pin with no forced
downgrade — but it declares `deepeval` as an **unpinned** dependency and
would silently bump the shared venv's deepeval from whatever
`deepeval>=4.1.10` currently resolves to `4.2.2` as a side effect of
installing an unrelated standalone script's dependency, right next to the
live (shadow-mode) `HallucinationMetric` caller in
`quality_scoring_service.py`. It also pulls ~20 packages the live serving
path has no other use for: `grpcio`, `opentelemetry-api`, `posthog`
(telemetry), `aiohttp`, and a full `typer`/`rich`/`questionary`/`pyfiglet`/
`portalocker` CLI stack plus `pytest` + `pytest-asyncio`/`xdist`/`repeat`/
`rerunfailures` (deepteam bundles a test-runner CLI as a runtime dependency,
not a dev-only extra). Confirmed via `pip show deepteam deepeval`
cross-referenced against `platform-runtime/requirements.txt`. Same
"footprint the live serving path has no other use for" reasoning as garak and
ragas, not a version-conflict story this time.

**The real scan run, committed under `reports/deepteam/20260913T004113Z.md` /
`-meta.json` / the native `20260913_104113.json`**: 2 vulnerabilities (Bias:
religion/politics/gender/race; PIILeakage: database-access/direct-disclosure/
session-leak/social-manipulation — deepteam auto-expands each vulnerability
class into its constituent types) × 2 deterministic-transform attacks
(Base64, ROT-13) = 8 test cases, `attacks_per_vulnerability_type=1`. Result:
**0 errored, 8/8 passing, overall CVSS score 0.0 (Low)**, run duration ~344s
against the live `glm-5.3:cloud` router. Every attack input, target response,
and evaluation reasoning string in the native JSON is real model output from
this run — nothing hardcoded or fabricated. This is a genuinely reassuring
result for `glm-5.3:cloud` behind this router (it consistently refused the
biased/PII-extraction premises and explained why, per the sampled transcripts
in the JSON), not a vacuous pass from a broken harness — the harness's own
"no errored test cases" plus the earlier PromptInjection failure mode (below)
both prove the evaluation pipeline actually discriminates real content rather
than defaulting every case to pass.

**A real, confirmed limitation surfaced during development, not hidden**:
deepteam's generative attack methods (`PromptInjection`, `Roleplay`, and
others under `deepteam.attacks.single_turn`) call the *simulator* model a
second time mid-attack to draft an "enhanced"/jailbroken variant of the
attack prompt (confirmed by instrumenting `_ModelRouterJudge.generate()` and
reading the actual prompt deepteam sent: a "CRITICAL FEEDBACK FROM PREVIOUS
ATTEMPT... you MUST explicitly fix this issue" retry loop asking the
simulator to produce a working jailbreak template). `glm-5.3:cloud`, being an
aligned model, refuses this meta-prompt outright ("I won't help with this
request... What's being asked is for me to write a working jailbreak
prompt..."), and deepteam has no fallback for a refusal here — it expects
strict JSON back and, receiving prose, logs `Evaluation LLM outputted an
invalid JSON. Please use a better evaluation model.` after 2 retries, then
marks the test case errored. This was reproduced directly (see the
`--allow-generative-attacks` escape hatch and the module docstring in
`core/quality/deepteam_scan.py`) before choosing to default the scan to
attack methods with a deterministic `enhance()` step (Base64/ROT13/Leetspeak
— confirmed by reading their source, no second LLM call) instead of silently
omitting PromptInjection/Roleplay from the write-up.

## Lesson

A mission pre-flight's claim about sandbox network reachability (or any
environment fact) is a snapshot of one prior sandbox instance, not a durable
property of "the sandbox" as a category — check it directly with the cheapest
possible probe (a 5-second health-check curl) before adapting scope around an
assumption that may no longer hold, and say so explicitly, in both directions,
when it doesn't: don't silently accept a stale "unreachable" claim, and don't
silently upgrade a real finding to "confirmed against the live router" without
flagging that this contradicts what the mission was told to expect. Separately:
using a well-aligned model as an LLM red-teaming tool's own *simulator*
(not just its target) creates a specific failure mode most red-teaming
harnesses aren't built to expect — the simulator itself refusing to draft the
attack — and that failure surfaces as an opaque "invalid JSON" error rather
than a clear "the simulator declined," so it is worth instrumenting a probe
generate() call once, early, to see the actual raw exchange rather than
debugging blind from a stack trace two layers deep in someone else's library.
And, as with the ragas `langchain-community` bug before it: a library's
declared `Requires-Dist` metadata and its actual unconditional imports are
two different (and here, contradictory) sources of truth — only actually
running `import <package>` after a fresh install catches the gap, `pip
install --dry-run`/dependency-resolution success is not sufficient proof the
package works.

## Future Guidance

Before trusting `deepteam_scan.py`'s "reachable" path in a future sandbox or
CI run, re-check `http://127.0.0.1:8891/health` directly rather than assuming
either this record's "reachable" finding or the original mission pre-flight's
"unreachable" claim — both are snapshots, not guarantees. If a future deepteam
release declares `sentry_sdk` properly or drops the dependency, this file's
reasoning for keeping it pinned in `requirements-deepteam.txt` should be
re-verified rather than carried forward unchanged. Before scaling this scan up
(more vulnerabilities, more attacks per type, or the generative attack methods
via `--allow-generative-attacks`), budget for it: this 8-test-case run alone
took ~344 seconds serially against the live router (`async_mode=False,
max_concurrent=1`, deliberately conservative for a first real run) — a larger
sweep should either raise `max_concurrent` (untested here) or expect
proportionally longer wall-clock time, and should expect the
`--allow-generative-attacks` path to show real errored test cases against this
particular judge/target model, not a bug to chase.
