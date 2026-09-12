# USS-TJR-MSN-0370 — supabase-py Investigation (follow-up to MSN-0369 Stream 4 / PR #157)

Date: 2026-09-12
Scope: real investigation of why Dependabot PR #157 (`supabase` 2.3.4 → 2.31.0, `telegram-bots/xo`) was deferred rather than merged, and whether `scoped_supabase.py`'s private-attribute monkeypatch has a clean, non-hacky replacement.

## TL;DR

- The private-attribute hack (`client._auth_token`) is confirmed dead — `SyncClient` was renamed to `Client` and the whole `_auth_token` mechanism it relied on was removed by supabase-py 2.5.0 (confirmed: 0 occurrences from 2.5.0 onward; still present, doing exactly what the old docstring described, at 2.3.4/2.4.2).
- **There is a real, public, non-hacky replacement**, and it's been available since supabase-py **2.4.3**, not just in the latest release: pass the scoped Authorization header through `ClientOptions(headers={"Authorization": f"Bearer {token}"})` at `create_client()` time. `_get_auth_headers()` was rewritten in 2.4.3 to read any Authorization the caller already put in `options.headers` instead of unconditionally deriving it from the key argument. Verified **empirically**, not just by reading source — a live `create_client()` call's resulting `client.postgrest.session.headers` had `apiKey == anon_key` and `Authorization == f"Bearer {scoped_token}"` as two genuinely independent values, tested on 2.4.3, 2.7.4, 2.24.0, and 2.31.0.
- `scoped_supabase.py` has been **redesigned to use this public API** and the private-attribute patch is gone from `telegram-bots/xo/scoped_supabase.py`.
- **PR #157's full target (2.31.0) is still blocked** — but for a different, more fundamental reason than the one that triggered the original deferral: `python-telegram-bot==20.7` (pinned in `telegram-bots/xo/requirements.txt`) hard-requires `httpx~=0.25.2`. Starting around supabase-py's own 2.9.x/postgrest-0.17.x line, its transitive deps (`postgrest`, `gotrue`) began calling `httpx.Client(..., proxy=...)` — the singular `proxy` kwarg httpx only added in 0.26 (replacing the old plural `proxies` kwarg). Under httpx<0.26 this is a hard crash: `TypeError: Client.__init__() got an unexpected keyword argument 'proxy'`. This is not hypothetical — reproduced live, and `pip install python-telegram-bot==20.7 supabase==2.31.0` gives a real `ResolutionImpossible` (`python-telegram-bot 20.7 depends on httpx~=0.25.2` / `supabase 2.31.0 depends on httpx<0.29 and >=0.26`).
- **This mission's actual code change**: bumped `telegram-bots/xo/requirements.txt`'s `supabase` pin from 2.3.4 to **2.7.4** (the highest release whose own declared `postgrest<0.17.0` bound still keeps postgrest below the `proxy=` line) and added an explicit `gotrue<2.9.0` pin (replacing the already-broken `gotrue==2.12.4` pin from PR #132 — see below). This unblocks dropping the monkeypatch now, on a version that's real and installable alongside PTB 20.7, without waiting on PR #157's full 2.31.0 target.

## Bonus finding: `gotrue==2.12.4` pin (PR #132, already merged) was already broken

While bisecting httpx compatibility, found that the *currently committed* `telegram-bots/xo/requirements.txt` (post-PR-#132, which bumped `gotrue` from 1.3.1 → 2.12.4) is **already unsatisfiable** together with the existing `httpx<0.26` pin:

```
pip install "supabase==2.3.4" "gotrue==2.12.4" "httpx<0.26"
ERROR: Cannot install gotrue==2.12.4, httpx<0.26 and supabase==2.3.4 because these package versions have conflicting dependencies.
The conflict is caused by:
    The user requested httpx<0.26
    supabase 2.3.4 depends on httpx<0.26 and >=0.24
    gotrue 2.12.4 depends on httpx<0.29 and >=0.26
```

Checked the actual live production venv (`/opt/starship-endeavour/telegram-bots/xo/.venv`): it still has **`gotrue==1.3.1`** installed, not 2.12.4. So PR #132 landed a `requirements.txt` change that was never actually applied to the running service — either the reinstall step was skipped, or it was attempted and silently failed. The bot has been running this whole time on the pre-#132 gotrue, and a fresh `pip install -r requirements.txt` on that file, as committed, would fail outright. Fixed as part of this mission's requirements.txt change (`gotrue<2.9.0` instead).

## Verification method

Not just changelog reading — installed every relevant version combination into throwaway venvs and either read the actual `supabase/_sync/client.py` source or ran a live `create_client()` call:

| Check | Result |
|---|---|
| `SyncClient` class name / `_auth_token` attribute | Present through 2.4.x; gone (renamed to `Client`, `_auth_token` mechanism removed) from 2.5.0 onward |
| `ClientOptions(headers={"Authorization": ...})` respected | **No** on 2.3.4/2.4.2 (unconditionally overwritten); **Yes** from 2.4.3 onward (confirmed live at 2.4.3, 2.7.4, 2.24.0, 2.31.0) |
| `postgrest` version pulled by `supabase==X` | `<0.17.0` for supabase 2.4.3–2.7.4; **`>=0.17.0` mandatory from supabase 2.8.1** |
| `postgrest==0.17.0` + httpx 0.25.2 | Crashes: `TypeError: Client.__init__() got an unexpected keyword argument 'proxy'` |
| `gotrue` version resolved when only `supabase==X` is pinned | Resolver picks newest allowed (often 2.9.1+, which has the same `proxy=` bug) unless `gotrue<2.9.0` is pinned explicitly |
| Full stack: `python-telegram-bot==20.7` + `supabase==2.7.4` + `gotrue<2.9.0` + `httpx<0.26` (+ apscheduler/dotenv/pyjwt/edge-tts, matching real requirements.txt) | **Resolves cleanly**, resolved versions: supabase 2.7.4, gotrue 2.8.1, httpx 0.25.2, postgrest 0.16.11, realtime 2.31.0 (no httpx dep), storage3 0.7.7, supafunc 0.5.1 |
| Live header-separation test on that exact resolved stack | `apiKey == anon_key`, `Authorization == f"Bearer {scoped_token}"`, genuinely independent — pass |
| `pip install -r telegram-bots/xo/requirements.txt` (post-fix) + `pytest telegram-bots/xo -q` | 14 passed |
| Redesigned `build_scoped_client()` end-to-end (with a stub that intercepts the real `create_client` call and forces the live-verify query to fail, so no real network needed) | `apiKey`/`Authorization` headers correctly separated; `None` returned on verification failure exactly as before — auth-fallback behavior unchanged |

## Why 2.31.0 (PR #157's actual target) is still blocked

`python-telegram-bot==20.7` needs `httpx~=0.25.2`. supabase-py 2.31.0 needs `httpx>=0.26,<0.29`. These ranges do not overlap — this is a hard `pip` `ResolutionImpossible`, confirmed directly, not an assumption. Getting to 2.31.0 requires upgrading `python-telegram-bot` past 20.7 first (its own httpx pin needs to move to `>=0.26`), which is separate, larger work (PTB's `HTTPXRequest`/proxy-handling changed across major versions — same class of breaking change this mission was warned to expect, just in a different package) and out of scope here. Note `telegram-bots/revs`'s bot already runs `python-telegram-bot==22.8` with `httpx<0.29` and has **no such conflict** — `pip install python-telegram-bot==22.8 supabase==2.31.0 "httpx<0.29"` resolves cleanly. If/when `telegram-bots/xo` is ever bumped to PTB 22.x (a separate decision, not attempted here), the full PR #157 target becomes trivially available with the same header-based redesign already shipped in this mission's `scoped_supabase.py`.

## Recommendation

- **PR #157 (2.3.4 → 2.31.0) stays deferred/closed** — confirmed blocked, for a concrete and now well-understood reason (PTB 20.7's httpx pin), not the originally-assumed "private API removed with no replacement" reason.
- **Safe intermediate bump shipped in this mission**: `supabase` 2.3.4 → **2.7.4** + explicit `gotrue<2.9.0`, with `scoped_supabase.py` rewritten to use the public `ClientOptions`-header API instead of the `_auth_token` monkeypatch. Verified installable, verified header-separation behavior, verified existing test suite (14/14) still green.
- **Path to the full PR #157 bump later**: upgrade `python-telegram-bot` in `telegram-bots/xo` past 20.7 (mirroring what `telegram-bots/capacitybot` and `telegram-bots/revs` already did in PRs #124/#151) to unpin `httpx<0.26`, then re-run this same version-bisection to confirm the ceiling moves — the redesigned `scoped_supabase.py` needs no further changes for that, since the ClientOptions-header approach already works unchanged at 2.31.0.
- **Also worth a small separate follow-up**: verify the live `tg-xo.service` venv is actually reinstalled against the new pin (it was silently stuck on the pre-#132 `gotrue==1.3.1` — see above) rather than assuming a `requirements.txt` change alone takes effect.

## Files touched

- `telegram-bots/xo/scoped_supabase.py` — dropped the `client._auth_token` private-attribute patch; now uses `create_client(url, anon_key, options=ClientOptions(headers={"Authorization": f"Bearer {token}"}))`. Docstring rewritten with the full mechanism history and the httpx/PTB blocker explanation.
- `telegram-bots/xo/requirements.txt` — `supabase` 2.3.4 → 2.7.4; `gotrue==2.12.4` → `gotrue<2.9.0` (fixing the already-broken pin from PR #132); comments explain both changes and the re-verification steps needed before ever bumping past 2.7.4 while PTB 20.7's httpx pin stands.

Not touched (out of scope for this mission, flagged only): `telegram-bots/revs/scoped_supabase.py` carries the identical `_auth_token` hack and the identical `supabase==2.3.4`/`gotrue==2.12.4` pins, but that bot's own `python-telegram-bot==22.8` has no httpx conflict — it could go straight to supabase 2.31.0 with the same redesign, a much easier follow-up than this one.
