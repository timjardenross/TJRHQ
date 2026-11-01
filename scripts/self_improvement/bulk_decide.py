"""
One-off bulk disposition of HQ Evolution opportunities (reject, with reasons).

Closes out the 2026-11-01 triage of the self-improvement list through the
dashboard's own decision endpoint (POST /api/opportunity/decide), so every
rule the dashboard enforces still applies. Run it ON THE VM, where the
dashboard listens (127.0.0.1:8892).

    python3 scripts/self_improvement/bulk_decide.py --list
    python3 scripts/self_improvement/bulk_decide.py             # dry run (default)
    python3 scripts/self_improvement/bulk_decide.py --apply

Safety, per item, before anything is sent:
  * the opportunity must exist (404 -> skipped);
  * its title must contain the expected text, so a reused or mistyped ID can
    never reject the wrong thing (mismatch -> skipped);
  * it must still be open (not already rejected/resolved/learned).
The default is a dry run. Nothing is written without --apply. Exit status is
non-zero if any item errored (skips are not errors).

Items the triage could not see (the "implementing" and "verifying" ones) can
be added without editing this file: run --list, then pass a JSON file of
    [{"id": "EVO-0xyz", "title_contains": "text", "reason": "why"}]
with --file. Entries from --file are added to the built-in list.

Stdlib only. The dashboard has no auth of its own (it binds to localhost and
Caddy fronts it); if SELF_IMPROVEMENT_API_SECRET is set it is sent as
X-Self-Improvement-Secret, matching the portal.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_BASE_URL = "http://127.0.0.1:8892"
BATCH_TAG = "[bulk triage 2026-11-01] "
OPEN_STATES = ("proposed", "investigating", "approved", "implementing", "verifying", "watching")

_ALREADY_DONE_457 = "Already implemented in PR #457 (merged 2026-10-25); the live store was never updated."


@dataclass(frozen=True)
class Item:
    id: str
    title_contains: str
    reason: str


BUILTIN_ITEMS: tuple[Item, ...] = (
    Item("EVO-0115", "playwright", _ALREADY_DONE_457),
    Item("EVO-0116", "postcss", _ALREADY_DONE_457),
    Item("EVO-0141", "@supabase/ssr", _ALREADY_DONE_457),
    Item("EVO-0142", "@supabase/supabase-js", _ALREADY_DONE_457),
    Item("EVO-0143", "@types/node",
         "Superseded by PR #473: aligned to the Node 22 types (engines.node >=22) instead of 26."),
    Item("EVO-0145", "next ",
         "Two major versions (14 -> 16); needs its own migration mission, not a bot version bump."),
    Item("EVO-0144", "knip",
         "Deferred: major bump of a dev-only tool, low value. Re-propose if needed."),
    Item("EVO-0126", "pylint",
         "Deferred: two majors, low value; repo use of pylint not verified. Re-propose if needed."),
    Item("EVO-0114", "Qwen-Image",
         "No concrete workload; unvetted uploader, unclear license, image model with no fit to HQ. "
         "Research was a template fallback (Model Router unreachable)."),
    Item("EVO-0118", "gemma-3-27b",
         "No concrete workload or GPU budget; Gemma license has use restrictions. Revisit with a real need."),
    Item("EVO-0119", "Qwen3-30B",
         "System-rated fit is weak and there is no concrete workload. Revisit with a real need."),
    Item("EVO-0120", "Qwen2.5-1.5B",
         "No concrete workload today; revisit if self-hosted inference becomes a goal."),
    Item("EVO-0121", "granite-3.1-2b",
         "No concrete workload today; revisit if self-hosted inference becomes a goal."),
    Item("EVO-0065", "lama-caravan",
         "No fleet of local nodes to route today; revisit if self-hosted inference becomes a goal."),
)


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status


def _request(base_url: str, method: str, path: str, payload: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    secret = os.environ.get("SELF_IMPROVEMENT_API_SECRET")
    if secret:
        headers["X-Self-Improvement-Secret"] = secret
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    # base_url is operator-supplied and defaults to the local dashboard.
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # nosec B310
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        raise ApiError(exc.code, body) from exc
    except urllib.error.URLError as exc:
        raise ApiError(0, f"cannot reach {base_url}: {exc.reason}") from exc


def list_open(base_url: str) -> list[dict]:
    out = _request(base_url, "GET", "/api/opportunities?state=" + ",".join(OPEN_STATES))
    return out.get("opportunities", [])


def check_item(base_url: str, item: Item) -> tuple[str, str]:
    """Return (verdict, detail). verdict is 'ok' or 'skip'; API errors raise."""
    try:
        opp = _request(base_url, "GET", f"/api/opportunity/{item.id}")
    except ApiError as exc:
        if exc.status == 404:
            return "skip", "not found"
        raise
    title = opp.get("title") or ""
    if item.title_contains.lower() not in title.lower():
        return "skip", f"title mismatch (expected to contain {item.title_contains!r}, got {title!r})"
    # The fine state is stage_detail on the simplified API and lifecycle_state
    # on the older one; either way it is one of OPEN_STATES while still open.
    state = opp.get("stage_detail") or opp.get("lifecycle_state")
    if state not in OPEN_STATES:
        return "skip", f"already {state}"
    return "ok", f"{state}: {title}"


def load_extra(path: str) -> list[Item]:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    items = []
    for entry in raw:
        missing = {"id", "title_contains", "reason"} - set(entry)
        if missing:
            raise SystemExit(f"{path}: entry {entry!r} is missing {sorted(missing)}")
        items.append(Item(entry["id"], entry["title_contains"], entry["reason"]))
    return items


def run(base_url: str, items: list[Item], apply: bool, out=sys.stdout) -> int:
    rejected = skipped = errors = 0
    for item in items:
        try:
            verdict, detail = check_item(base_url, item)
            if verdict == "skip":
                skipped += 1
                print(f"SKIP    {item.id}  {detail}", file=out)
                continue
            if not apply:
                print(f"WOULD   {item.id}  reject  <- {detail}\n          reason: {item.reason}", file=out)
                continue
            _request(base_url, "POST", "/api/opportunity/decide", {
                "opportunity_id": item.id,
                "decision_type": "reject",
                "reasoning": BATCH_TAG + item.reason,
            })
            rejected += 1
            print(f"REJECT  {item.id}  {detail}", file=out)
        except ApiError as exc:
            errors += 1
            print(f"ERROR   {item.id}  {exc}", file=out)
    mode = "applied" if apply else "dry run (nothing written; pass --apply)"
    print(f"\n{mode}: {rejected} rejected, {skipped} skipped, {errors} errors, "
          f"{len(items)} items", file=out)
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default=os.environ.get("SELF_IMPROVEMENT_API_URL", DEFAULT_BASE_URL))
    parser.add_argument("--list", action="store_true", help="list open opportunities and exit")
    parser.add_argument("--file", help="JSON file of extra items to reject")
    parser.add_argument("--apply", action="store_true", help="actually send the rejections")
    args = parser.parse_args(argv)

    if args.list:
        try:
            opps = list_open(args.base_url)
        except ApiError as exc:
            print(f"ERROR {exc}")
            return 1
        for o in sorted(opps, key=lambda o: (o.get("lifecycle_state") or "", o.get("opportunity_id") or "")):
            print(f"{o.get('opportunity_id'):10} {o.get('lifecycle_state'):14} "
                  f"{(o.get('mission_id') or '-'):28} {o.get('title')}")
        print(f"\n{len(opps)} open")
        return 0

    items = list(BUILTIN_ITEMS) + (load_extra(args.file) if args.file else [])
    return run(args.base_url, items, args.apply)


if __name__ == "__main__":
    sys.exit(main())
