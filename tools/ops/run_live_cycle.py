#!/usr/bin/env python3
"""One consolidated VM command: collect, generate products, verify; plus a missed-brief drill. Run ON THE VM as the service user:

    cd /opt/starship-endeavour && platform-runtime/run-with-infisical-bot.sh xo -- \\
        platform-runtime/.venv/bin/python -m tools.ops.run_live_cycle [--dry-run] [--drill-missed-brief]

Steps (each prints PASS / FAIL / SKIPPED; a JSON report is always written, see --report):
  1 preflight  env presence (names only), Supabase read, Firecrawl budget read, run lock, previous-run guard
  2 collect    calls the scheduler's own job functions once: _daily_collection_job (incl. Firecrawl sources),
               _intraday_status_collection_job, _intraday_media_collection_job. No scheduler is started.
  3 products   intel_products_job.run(force=True): one upsert per product into intelligence_products. No send_weekly.
  4 verify     tools/intelligence/verify_operational (PR #734) over GET-only reads: PASS only with evidence rows,
               otherwise NOT_YET_OBSERVABLE. The checklist is never edited.

Guards (all in-process, nothing on disk or in the environment changes):
  - no delivery: TELEGRAM_*/SLACK_* env vars and INTEL_PRODUCTS_WEEKLY_TELEGRAM are removed from this process; notify(),
    the outage-alert push and core_events publishing (what the attention poller turns into pushes) are replaced by
    record-only stubs; urlopen refuses api.telegram.org / slack hosts. The run aborts if any send was attempted.
  - no checkpoint movement: heartbeat writes (intelligence_collection, intraday_*) are record-only, so the deadman and
    the 20:01Z brief state are untouched; send_brief/brief jobs are never called.
  - idempotent: events dedupe on dedup_hash/canonical_url, products upsert on (product_key, generated_for); a rerun inside
    --min-recollect-minutes skips collection (credit guard) unless --force-recollect.
  - bounded: Firecrawl sources are dropped when headroom < --max-firecrawl-credits (the 1700/850 circuit breaker still
    applies per call); a SIGALRM kills the run after --max-runtime-seconds; one run at a time (flock).
  - source_health rows and intelligence_events/products are the only writes (the same ones the scheduler makes).

Drill (--drill-missed-brief): see run_drill. Reads production rows by SELECT only, evaluates the deadman/catch-up logic for
a hypothetical brief_date with record-only stubs and a drill clock, and refuses to run unless the stubs are in place.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import logging
import os
import signal
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "platform-runtime")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PASS, FAIL, SKIPPED = "PASS", "FAIL", "SKIPPED"
BLOCKED_HOSTS = ("api.telegram.org", "telegram.org", "hooks.slack.com", "slack.com")
SECRET_PREFIXES = ("TELEGRAM_", "SLACK_")
FLAG_ALWAYS_OFF = "INTEL_PRODUCTS_WEEKLY_TELEGRAM"
REQUIRED_ENV = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
OPTIONAL_ENV = ("FIRECRAWL_API_KEY", "FIRECRAWL_API_KEY_2", "INTEL_PROVENANCE_COLUMNS", "INTEL_PRODUCTS_ENABLED", "INTELLIGENCE_PAUSED_SOURCES",
                "SHADOW_MODE_SCORING_ENABLED", "BRIEF_DEADMAN_SKIP_DATES")
STATE_DIR = Path(os.environ.get("LIVE_CYCLE_STATE_DIR", "/tmp/uss-tjr-live-cycle"))
JOBS = (("daily_sweep", "_daily_collection_job", "intelligence_collection"),
        ("intraday_status", "_intraday_status_collection_job", "intraday_status_collection"),
        ("intraday_media", "_intraday_media_collection_job", "intraday_media_collection"))
log = logging.getLogger("run_live_cycle")


class RunTimeout(Exception):
    pass


class Refused(Exception):
    """A safety guard is not in place; nothing was run."""


@dataclass
class Step:
    name: str
    status: str = SKIPPED
    detail: str = ""
    data: dict = field(default_factory=dict)

    def show(self) -> None:
        print(f"[{self.status:7}] {self.name}: {self.detail}", flush=True)


# ── delivery guard ─────────────────────────────────────────────────────────────────────────────────────────────
class DeliveryGuard(contextlib.AbstractContextManager):
    """Everything that could send a message or advance a job checkpoint is replaced by a recorder for the life of the run."""

    def __init__(self):
        self.attempts: list[dict] = []     # anything that tried to send (must stay empty)
        self.suppressed: list[dict] = []   # record-only calls made by the guarded job paths (expected)
        self.env_removed: list[str] = []
        self._undo: list = []

    def _patch(self, obj, attr, new):
        self._undo.append((obj, attr, getattr(obj, attr)))
        setattr(obj, attr, new)

    def __enter__(self):
        for k in list(os.environ):
            if k.startswith(SECRET_PREFIXES) or k == FLAG_ALWAYS_OFF:
                self.env_removed.append(k)       # names only
                del os.environ[k]
        real_urlopen = urllib.request.urlopen

        def guarded_urlopen(req, *a, **kw):
            url = req if isinstance(req, str) else getattr(req, "full_url", "")
            host = (urllib.parse.urlparse(url).hostname or "").lower()
            if any(host == h or host.endswith("." + h) for h in BLOCKED_HOSTS):
                self.attempts.append({"kind": "http", "host": host})
                raise ConnectionRefusedError(f"live-cycle guard: delivery host {host} blocked")
            return real_urlopen(req, *a, **kw)
        guarded_urlopen._live_cycle_guard = True
        self._patch(urllib.request, "urlopen", guarded_urlopen)

        def rec(kind, ret=None):
            def f(*a, **kw):
                self.suppressed.append({"kind": kind, "args": str(a)[:100]})
                return ret
            f._record_only = True
            return f

        class _NotOk:
            ok = False
        for modname, attr, kind, ret in (("core.platform.notification_service", "notify", "notify", _NotOk()),
                                         ("core.platform.event_bus", "publish_event", "core_events", None),
                                         ("core.platform.heartbeat", "record_heartbeat", "heartbeat", True),
                                         ("intelligence.persistence.intelligence_store", "_maybe_push_outage_alert", "outage_alert_push", None),
                                         ("intelligence.persistence.intelligence_store", "_publish_core_event", "core_events", None)):
            try:
                mod = __import__(modname, fromlist=["x"])
                if hasattr(mod, attr):
                    self._patch(mod, attr, rec(kind, ret))
            except Exception as exc:  # noqa: BLE001 - a module that cannot import cannot send either
                log.info("guard: %s not patched (%s)", modname, exc)
        return self

    def __exit__(self, *exc):
        for obj, attr, orig in reversed(self._undo):
            setattr(obj, attr, orig)
        return False

    def patch_scheduler(self, sched) -> None:
        def hb(*a, **kw):
            self.suppressed.append({"kind": "heartbeat", "args": str(a)[:100]})
        hb._record_only = True
        self._patch(sched, "_record_heartbeat", hb)

    @property
    def clean(self) -> bool:
        return not self.attempts


# ── Supabase GET ───────────────────────────────────────────────────────────────────────────────────────────────
def rest_get(table: str, query: str) -> list[dict]:
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set")
    req = urllib.request.Request(f"{url.rstrip('/')}/rest/v1/{table}?{query}", headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310 - SUPABASE_URL env, https
        return json.loads(r.read())


# ── step 1: preflight ──────────────────────────────────────────────────────────────────────────────────────────
def env_report() -> dict:
    return {"required_present": {k: bool(os.environ.get(k)) for k in REQUIRED_ENV},
            "optional": {k: ("set" if os.environ.get(k) else "unset") for k in OPTIONAL_ENV},
            "INTEL_PROVENANCE_COLUMNS_value": os.environ.get("INTEL_PROVENANCE_COLUMNS", "")[:20] or None}


def firecrawl_headroom(usage_fn=None) -> dict:
    """Read-only usage per Firecrawl account. {provider: {call_count, ceiling, headroom}} or {'error': ...}."""
    out = {}
    try:
        if usage_fn is None:
            from intelligence.ingestion import external_fetch_budget as efb
            usage_fn = efb.current_usage
        for prov in ("firecrawl", "firecrawl_2"):
            u = usage_fn(prov)
            out[prov] = {"call_count": u["call_count"], "ceiling": u["ceiling"], "headroom": u["headroom"]}
    except Exception as exc:  # noqa: BLE001 - unreadable budget means: spend nothing
        out["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return out


def previous_run_guard(min_minutes: int, state_dir: Path = STATE_DIR, now: datetime | None = None) -> dict | None:
    """The most recent report whose collection actually ran inside the window, else None."""
    now = now or datetime.now(timezone.utc)
    best = None
    for f in sorted(state_dir.glob("last-collection-*.json")) if state_dir.exists() else []:
        try:
            t = datetime.fromisoformat(json.loads(f.read_text())["finished_at"])
        except (OSError, ValueError, KeyError):
            continue
        if now - t < timedelta(minutes=min_minutes) and (best is None or t > best[0]):
            best = (t, f.name)
    return {"finished_at": best[0].isoformat(), "file": best[1]} if best else None


@contextlib.contextmanager
def run_lock(state_dir: Path = STATE_DIR):
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fh = open(state_dir / "run.lock", "w")  # noqa: SIM115 - held for the whole run
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        raise Refused("another live-cycle run holds the lock") from None
    try:
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


# ── step 2: collection through the scheduler's own job functions ───────────────────────────────────────────────
class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)

    def attach(self, logger: logging.Logger) -> None:
        self._logger, self._level = logger, logger.level
        logger.addHandler(self)
        if not logger.isEnabledFor(logging.INFO):
            logger.setLevel(logging.INFO)

    def detach(self) -> None:
        self._logger.removeHandler(self)
        self._logger.setLevel(self._level)


class CollectionRecorder:
    """Wraps collection_engine.collect_all: same call, plus per-source results and an optional Firecrawl source exclusion."""

    def __init__(self, real, firecrawl_names, exclude_firecrawl: bool, load_registry):
        self.real, self.fc_names, self.exclude_fc, self.load_registry = real, set(firecrawl_names), exclude_firecrawl, load_registry
        self.sources: dict[str, dict] = {}
        self.calls = 0
        self.skipped_firecrawl: list[str] = []

    def __call__(self, sources=None, max_workers=8):
        self.calls += 1
        if sources is None:
            sources = self.load_registry()
        if self.exclude_fc:
            self.skipped_firecrawl += [s.source_name for s in sources if s.source_name in self.fc_names]
            sources = [s for s in sources if s.source_name not in self.fc_names]
        items, health = self.real(sources=sources, max_workers=max_workers)
        counts: dict[str, int] = {}
        for it in items:
            counts[it.source_name] = counts.get(it.source_name, 0) + 1
        for h in health:
            self.sources[h.source_name] = {"status": h.status, "items_retrieved": h.items_retrieved, "items_collected": counts.get(h.source_name, 0),
                                           "content_valid": h.content_valid, "error": (h.error_message or "")[:160] or None,
                                           "firecrawl_path": h.source_name in self.fc_names}
        return items, health


def run_collection(args, guard: DeliveryGuard, budget: dict) -> list[Step]:
    steps = []
    try:
        import intelligence.scheduler as sched
        from intelligence.ingestion import collection_engine as ce
        from intelligence.persistence import intelligence_store as store
    except Exception as exc:  # noqa: BLE001
        return [Step("collect", FAIL, f"cannot import the scheduler job functions: {type(exc).__name__}: {exc}")]
    guard.patch_scheduler(sched)
    primary_ok = "error" not in budget and budget.get("firecrawl", {}).get("headroom", 0) >= args.max_firecrawl_credits
    exclude_fc = not primary_ok
    cap = _LogCapture()
    cap.attach(sched.log)
    real_collect, real_filter = ce.collect_all, store.filter_unpersisted_events
    new_by_source: dict[str, int] = {}

    def counting_filter(events):
        kept = real_filter(events)
        for e in kept:
            new_by_source[e.source_name] = new_by_source.get(e.source_name, 0) + 1
        return kept
    try:
        store.filter_unpersisted_events = counting_filter
        for label, fn_name, hb_key in JOBS:
            if time.monotonic() > args.deadline:
                steps.append(Step(f"collect:{label}", SKIPPED, "runtime budget exhausted"))
                continue
            rec = CollectionRecorder(real_collect, sched._FIRECRAWL_FETCH_SOURCE_NAMES, exclude_fc, store.load_source_registry)
            ce.collect_all = rec
            before = len(cap.records)
            new_by_source.clear()
            t0 = time.monotonic()
            getattr(sched, fn_name)()          # the scheduler's own function; swallows its own errors, so we read its log
            errs = [r.getMessage()[:200] for r in cap.records[before:] if r.levelno >= logging.ERROR]
            summary = next((r.getMessage() for r in reversed(cap.records[before:]) if "complete:" in r.getMessage()), None)
            bad = {k: v for k, v in rec.sources.items() if v["status"] != "ok"}
            data = {"seconds": round(time.monotonic() - t0, 1), "collect_all_calls": rec.calls, "job_summary_log": summary, "errors": errs,
                    "sources_checked": len(rec.sources), "sources_not_ok": len(bad), "new_events_after_dedupe": sum(new_by_source.values()),
                    "firecrawl_sources_skipped_for_budget": rec.skipped_firecrawl,
                    "per_source": {k: {**v, "new_events": new_by_source.get(k, 0)} for k, v in sorted(rec.sources.items())}}
            if errs:
                steps.append(Step(f"collect:{label}", FAIL, errs[0], data))
            elif not rec.calls or not rec.sources:
                steps.append(Step(f"collect:{label}", SKIPPED, "the job found no eligible source (it logged a warning and returned)", data))
            else:
                note = f"; {len(rec.skipped_firecrawl)} Firecrawl source(s) skipped (budget/credentials)" if rec.skipped_firecrawl else ""
                steps.append(Step(f"collect:{label}", PASS, f"{len(rec.sources)} sources, {len(bad)} not ok, {sum(v['items_collected'] for v in rec.sources.values())} items, "
                                  f"{sum(new_by_source.values())} new after dedupe{note}", data))
    finally:
        ce.collect_all, store.filter_unpersisted_events = real_collect, real_filter
        cap.detach()
    return steps


# ── step 3: products ───────────────────────────────────────────────────────────────────────────────────────────
def run_products(args, getter=None, writer=None, now: datetime | None = None) -> Step:
    getter = getter or rest_get
    try:
        getter("intelligence_products", "select=product_key&limit=1")
    except Exception as exc:  # noqa: BLE001
        return Step("products", FAIL, f"intelligence_products not readable ({type(exc).__name__}: {str(exc)[:120]}); is migration 0261 applied?")
    try:
        from intelligence import intel_products_job as job
        kw = {"getter": getter, "force": True, "as_of": now or datetime.now(timezone.utc)}
        if writer is not None:
            kw["writer"] = writer
        products = job.run(**kw)    # run() only fetches (GET) and upserts; send_weekly is never called
    except Exception as exc:  # noqa: BLE001
        return Step("products", FAIL, f"generation failed: {type(exc).__name__}: {str(exc)[:200]}")
    keys = [p["product_key"] for p in products]
    return Step("products", PASS if len(keys) == 3 else FAIL, f"generated and upserted {keys} for {(now or datetime.now(timezone.utc)).date()} (no Telegram path)",
                {"product_keys": keys, "exceptions": {p["product_key"]: len(p["exceptions"]) for p in products}})


# ── step 4: verification ───────────────────────────────────────────────────────────────────────────────────────
def run_verify(args, results: dict | None = None, getter=None, now: datetime | None = None) -> tuple[Step, dict | None]:
    from tools.intelligence import verify_operational as vo
    from tools.ops import live_cycle_queries as q
    now = now or datetime.now(timezone.utc)
    dep = vo._ts(args.deployed_at)
    try:
        if results is None:
            results = q.collect_results(getter or rest_get, now, sweep_hour=args.sweep_hour_utc, deployed_at=dep,
                                        journal=None if args.no_journal else q.read_deadman_journal)
        else:
            now = vo._ts((vo.rows(results, "as_of") or [{}])[0].get("as_of")) or now
        res = vo.evaluate(results, now=now, deployed_at=dep, sweep_hour=args.sweep_hour_utc, current=vo.read_checklist())
    except Exception as exc:  # noqa: BLE001
        return Step("verify", FAIL, f"verification could not run: {type(exc).__name__}: {str(exc)[:200]}"), None
    doc = vo.to_json(res, now, dep)
    tally = {v: sum(r.verdict == v for r in res) for v in (vo.PASS, vo.FAIL, vo.NYO)}
    for r in res:
        print(f"    {r.verdict:18} {r.name}", flush=True)
        for c in r.checks:
            if c.verdict != vo.PASS:
                print(f"        [{c.verdict}] {c.title}: {c.detail[:160]}", flush=True)
    detail = f"{tally[vo.PASS]} PASS (evidenced), {tally[vo.FAIL]} FAIL, {tally[vo.NYO]} NOT_YET_OBSERVABLE"
    return Step("verify", FAIL if tally[vo.FAIL] else PASS, detail, {"tally": tally, "report": doc, "meta": results.get("_meta")}), doc


# ── missed-brief drill ─────────────────────────────────────────────────────────────────────────────────────────
def _stub(kind: str, calls: list, ret=True):
    def f(*a, **kw):
        calls.append({"kind": kind, "args": str(a)[:160], "kwargs": str(kw)[:80]})
        return ret
    f._record_only = True
    return f


def run_drill(getter, *, source: str, now: datetime | None = None, tz_name: str = "Australia/Melbourne") -> list[Step]:
    """Prove detection + recovery on the production plumbing without delivery.

    ``getter(table, query)`` is the production GET path (captains_brief._sb_request on the VM). Real rows are only read. A hypothetical
    brief_date (latest stored date + 2 days, verified to have no row) is evaluated at a drill clock of 08:30 local on that date.
    Delivery caveat (rehearsal stream C): br._delivery/_alerted/_caught_up are in-process memory of the scheduler process only; the
    drill uses its own empty state and restores the module's, and shows that a fresh process sees a stored row as 'ok' even when
    Telegram delivery had failed ('alerted_undelivered' needs that memory)."""
    from zoneinfo import ZoneInfo

    from intelligence import brief_reliability as br
    now = now or datetime.now(timezone.utc)
    steps: list[Step] = []
    sql_log: list[dict] = []

    def ro_get(table, query=""):
        sql_log.append({"table": table, "query": query[:140]})
        if table != "captains_daily_briefs":
            raise Refused(f"drill read of unexpected table {table}")
        return getter(table, query)

    def snapshot(date_):
        rows = ro_get("captains_daily_briefs", "select=brief_type,brief_date,generated_at&order=generated_at.desc&limit=8")
        hyp = ro_get("captains_daily_briefs", f"select=brief_type,brief_date&brief_date=eq.{date_}&brief_type=eq.morning&limit=5")
        return {"latest": rows, "rows_for_hypothetical_date": len(hyp)}

    latest = ro_get("captains_daily_briefs", "select=brief_type,brief_date,generated_at&brief_type=eq.morning&order=brief_date.desc&limit=1")
    if not latest:
        return [Step("drill", FAIL, "no morning brief row to anchor the drill")]
    real_date = str(latest[0]["brief_date"])[:10]
    hyp_date = (datetime.fromisoformat(real_date).date() + timedelta(days=2)).isoformat()
    drill_now = datetime.fromisoformat(f"{hyp_date}T08:30:00").replace(tzinfo=ZoneInfo(tz_name)).astimezone(timezone.utc)
    before = snapshot(hyp_date)
    steps.append(Step("drill:anchor", PASS if before["rows_for_hypothetical_date"] == 0 else FAIL,
                      f"source={source}; latest real morning brief_date={real_date} generated {latest[0]['generated_at']}; hypothetical brief_date={hyp_date} has "
                      f"{before['rows_for_hypothetical_date']} row(s); drill clock {drill_now:%Y-%m-%d %H:%MZ}", {"before": before}))
    if steps[-1].status == FAIL:
        return steps

    notify_calls: list[dict] = []
    send_calls: list[dict] = []
    heartbeats: list[dict] = []
    notify, send = _stub("notify", notify_calls), _stub("send_brief", send_calls)
    # refuse unless the transport and send are record-only; state is local so the real module memory is untouched
    if not getattr(urllib.request.urlopen, "_live_cycle_guard", False):
        raise Refused("delivery guard is not installed (run through main())")
    if not (getattr(notify, "_record_only", False) and getattr(send, "_record_only", False)) or os.environ.get("TELEGRAM_BOT_TOKEN"):
        raise Refused("alert transport / brief send are not stubbed record-only, or a Telegram token is present")

    alerted, delivery, done = set(), {}, set()
    pure = []
    r1 = br.check_missed_brief(ro_get, notify, hyp_date, "morning", alerted=alerted, delivery=delivery)
    r2 = br.check_missed_brief(ro_get, notify, hyp_date, "morning", alerted=alerted, delivery=delivery)
    pure.append(("detects the miss", r1 == "alerted", {"first_call": r1}))
    pure.append(("alerts exactly once", len(notify_calls) == 1 and r2 == "already_alerted" and "MISSED BRIEF" in notify_calls[0]["args"],
                 {"second_call": r2, "alerts_recorded": len(notify_calls), "text": notify_calls[0]["args"] if notify_calls else None}))
    gap = br.get_gap(ro_get, hyp_date, drill_now)
    pure.append(("gap-aware lookback extends", gap.missed and gap.lookback_hours > br.BASE_LOOKBACK_HOURS,
                 {"lookback_hours": gap.lookback_hours, "gap_hours": gap.gap_hours, "capped": gap.capped}))
    c1 = br.catch_up_morning(ro_get, lambda: send("morning", catch_up=True), now_utc=drill_now, tz_name=tz_name, done=done)
    c2 = br.catch_up_morning(ro_get, lambda: send("morning", catch_up=True), now_utc=drill_now, tz_name=tz_name, done=done)
    pure.append(("would recover (catch-up sends once)", c1 == "sent" and c2 == "already_done" and len(send_calls) == 1,
                 {"first_call": c1, "second_call": c2, "sends_recorded": len(send_calls)}))
    # delivery-memory caveat on the real latest row (read only)
    key = ("morning", real_date)
    mem_alerted, mem = set(), {key: False}
    n_before = len(notify_calls)
    with_memory = br.check_missed_brief(ro_get, notify, real_date, "morning", alerted=mem_alerted, delivery=mem)
    fresh_process = br.check_missed_brief(ro_get, notify, real_date, "morning", alerted=set(), delivery={})
    pure.append(("delivery-memory caveat shown", with_memory == "alerted_undelivered" and fresh_process == "ok" and len(notify_calls) == n_before + 1,
                 {"with_in_process_memory": with_memory, "after_restart_empty_memory": fresh_process,
                  "meaning": "a stored row proves generation, not delivery; a failed Telegram send is only known to the scheduler process that saw it"}))
    for name, ok, ev in pure:
        steps.append(Step(f"drill:{name}", PASS if ok else FAIL, json.dumps(ev, default=str)[:300], ev))

    # wiring: the scheduler's own deadman/catch-up job functions, with the same stubs and a drill clock
    steps.append(_drill_scheduler_wiring(br, ro_get, hyp_date, drill_now, notify_calls, send_calls, heartbeats))

    after = snapshot(hyp_date)
    unchanged = before == after
    writes = [s for s in sql_log if s["table"] != "captains_daily_briefs"]
    steps.append(Step("drill:real state unchanged", PASS if unchanged and not writes else FAIL,
                      f"latest rows and hypothetical-date row count identical before/after; {len(sql_log)} GET-only reads of captains_daily_briefs; "
                      f"module state restored; stubs recorded {len(notify_calls)} alert(s) and {len(send_calls)} send(s), none delivered",
                      {"before": before, "after": after, "reads": len(sql_log)}))
    return steps


def _drill_scheduler_wiring(br, ro_get, hyp_date, drill_now, notify_calls, send_calls, heartbeats) -> Step:
    try:
        import intelligence.scheduler as sched
        from intelligence import captains_brief as cb
    except Exception as exc:  # noqa: BLE001
        return Step("drill:scheduler wiring", SKIPPED, f"scheduler not importable here ({type(exc).__name__}: {str(exc)[:100]}); pure logic above still proven")

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return drill_now.astimezone(tz) if tz else drill_now.replace(tzinfo=None)
    saved = {(o, a): getattr(o, a) for o, a in ((cb, "_sb_request"), (cb, "_send_telegram"), (cb, "send_brief"), (br, "brief_date_aest"), (br, "datetime"),
                                                (sched, "_record_heartbeat"))}
    mem = (set(br._alerted), dict(br._delivery), set(br._caught_up))
    n0, s0 = len(notify_calls), len(send_calls)
    cap = _LogCapture()
    cap.attach(sched.log)
    try:
        br._alerted.clear(), br._delivery.clear(), br._caught_up.clear()
        cb._sb_request = ro_get
        cb._send_telegram = _stub("notify(scheduler)", notify_calls)
        cb.send_brief = _stub("send_brief(scheduler)", send_calls)
        br.brief_date_aest = lambda now=None: hyp_date
        br.datetime = FakeDT
        sched._record_heartbeat = _stub("heartbeat", heartbeats, None)
        sched._brief_deadman_job()
        sched._brief_deadman_job()
        sched._morning_catch_up_job()
        sched._morning_catch_up_job()
        msgs = [r.getMessage() for r in cap.records]
    finally:
        for (o, a), v in saved.items():
            setattr(o, a, v)
        br._alerted.clear(), br._delivery.clear(), br._caught_up.clear()
        br._alerted.update(mem[0]), br._delivery.update(mem[1]), br._caught_up.update(mem[2])
        cap.detach()
    alerts, sends = len(notify_calls) - n0, len(send_calls) - s0
    ev = {"alerts_recorded": alerts, "sends_recorded": sends, "log": [m for m in msgs if "deadman" in m.lower() or "catch-up" in m.lower()][:4]}
    ok = alerts == 1 and sends == 1 and any("alerted" in m for m in msgs) and any("already_alerted" in m for m in msgs) and any("sent" in m for m in msgs)
    return Step("drill:scheduler wiring", PASS if ok else FAIL, "scheduler._brief_deadman_job x2 and _morning_catch_up_job x2: " + json.dumps(ev, default=str)[:300], ev)


# ── main ───────────────────────────────────────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tools.ops.run_live_cycle", description="Collect once, generate products, verify; or run the missed-brief drill.")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and run only the read-only preflight and verification; collect/products are SKIPPED")
    ap.add_argument("--drill-missed-brief", action="store_true", help="run only the missed-brief drill (SELECT-only, record-only stubs)")
    ap.add_argument("--drill-fixture-rows", help="sandbox only: JSON list of captains_daily_briefs rows replacing the production read (marked as fixture)")
    ap.add_argument("--verify-results", help="sandbox only: evaluate an exported results JSON (verify_operational shape) instead of production reads")
    ap.add_argument("--skip", action="append", default=[], choices=["collect", "products", "verify"])
    ap.add_argument("--max-firecrawl-credits", type=int, default=30, help="drop Firecrawl sources unless the primary account has at least this headroom (default 30)")
    ap.add_argument("--min-recollect-minutes", type=int, default=120)
    ap.add_argument("--force-recollect", action="store_true")
    ap.add_argument("--max-runtime-seconds", type=int, default=1500)
    ap.add_argument("--deployed-at", default=None, help="release boundary for verify_operational (UTC ISO)")
    ap.add_argument("--sweep-hour-utc", type=int, default=19)
    ap.add_argument("--no-journal", action="store_true", help="do not read journalctl for the deadman evidence")
    ap.add_argument("--report", help="JSON report path (default: <state dir>/live-cycle-<UTC stamp>.json)")
    return ap


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")


def main(argv: list[str] | None = None, *, getter=None) -> int:
    args = build_parser().parse_args(argv)
    from tools.intelligence import verify_operational as vo
    args.deployed_at = args.deployed_at or vo.DEFAULT_DEPLOYED_AT
    started = datetime.now(timezone.utc)
    args.deadline = time.monotonic() + args.max_runtime_seconds
    report_path = Path(args.report) if args.report else STATE_DIR / f"live-cycle-{started:%Y%m%dT%H%M%SZ}.json"
    report: dict = {"started_at": started.isoformat(), "mode": "drill" if args.drill_missed_brief else "dry-run" if args.dry_run else "live", "steps": [], "args": vars(args) | {"deadline": None}}
    steps: list[Step] = []
    report["steps"] = steps
    exit_code = 0

    def add(s: Step):
        s.show()
        steps.append(s)
        return s
    def _on_alarm(*_):
        raise RunTimeout()
    signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(args.max_runtime_seconds)
    guard = DeliveryGuard()
    try:
        with run_lock(), guard:
            print(f"LIVE CYCLE {report['mode']} started {started:%Y-%m-%d %H:%M:%SZ}; delivery guard on (removed env names: {guard.env_removed or 'none'})", flush=True)
            if args.drill_missed_brief:
                if args.drill_fixture_rows:
                    rows = json.loads(Path(args.drill_fixture_rows).read_text())
                    getter, source = (lambda t, q: _fixture_get(rows, q)), "FIXTURE (not production)"
                else:
                    from intelligence import captains_brief as cb
                    getter, source = cb._sb_request, "production captains_brief._sb_request (GET)"
                for s in run_drill(getter, source=source):
                    add(s)
            else:
                env = env_report()
                missing = [k for k, v in env["required_present"].items() if not v]
                budget = {} if args.verify_results else firecrawl_headroom()
                add(Step("preflight", FAIL if missing and not args.verify_results else PASS,
                         f"env missing: {missing or 'none'}; firecrawl headroom {budget or 'n/a'}; flags INTEL_PROVENANCE_COLUMNS={env['INTEL_PROVENANCE_COLUMNS_value']!r}", {"env": env, "firecrawl_budget": budget}))
                if missing and not args.verify_results:
                    raise Refused("Supabase credentials missing: run through run-with-infisical-bot.sh")
                prev = None if args.force_recollect else previous_run_guard(args.min_recollect_minutes)
                if "collect" in args.skip or args.dry_run or prev:
                    why = "--skip" if "collect" in args.skip else "dry-run: would run _daily_collection_job, _intraday_status_collection_job, _intraday_media_collection_job once" if args.dry_run \
                        else f"collection already ran at {prev['finished_at']} (< {args.min_recollect_minutes} min ago; --force-recollect to override)"
                    add(Step("collect", SKIPPED, why, {"previous": prev}))
                else:
                    cs = run_collection(args, guard, budget)
                    for s in cs:
                        add(s)
                    after = firecrawl_headroom()
                    spent = {p: after[p]["call_count"] - budget[p]["call_count"] for p in after if p in budget and isinstance(after[p], dict) and isinstance(budget.get(p), dict)}
                    over = [p for p, n in spent.items() if n > args.max_firecrawl_credits]
                    add(Step("collect:firecrawl credits", FAIL if over else PASS, f"spent this run {spent or 'unknown'} (cap {args.max_firecrawl_credits}); after {after}", {"spent": spent}))
                    if any(s.status == PASS for s in cs):
                        STATE_DIR.mkdir(parents=True, exist_ok=True)
                        (STATE_DIR / f"last-collection-{started:%Y%m%dT%H%M%SZ}.json").write_text(json.dumps({"finished_at": datetime.now(timezone.utc).isoformat()}))
                if "products" in args.skip or args.dry_run:
                    add(Step("products", SKIPPED, "--skip" if "products" in args.skip else "dry-run: would run intel_products_job.run(force=True), upsert 3 rows, no Telegram"))
                elif not guard.clean:
                    add(Step("products", SKIPPED, "a delivery attempt was recorded; stopping"))
                else:
                    add(run_products(args, getter=getter))
                if "verify" in args.skip:
                    add(Step("verify", SKIPPED, "--skip"))
                else:
                    results = json.loads(Path(args.verify_results).read_text()) if args.verify_results else None
                    s, doc = run_verify(args, results, getter=getter)
                    add(s)
                    report["verification"] = doc
            add(Step("delivery guard", PASS if guard.clean else FAIL,
                     f"{len(guard.attempts)} send attempt(s); {len(guard.suppressed)} record-only call(s) {dict_count(guard.suppressed)}", {"attempts": guard.attempts}))
    except Refused as exc:
        add(Step("refused", FAIL, str(exc)))
        exit_code = 3
    except RunTimeout:
        add(Step("timeout", FAIL, f"aborted after {args.max_runtime_seconds}s"))
        exit_code = 4
    except Exception as exc:  # noqa: BLE001 - always produce a report
        add(Step("error", FAIL, f"{type(exc).__name__}: {exc}"))
        exit_code = 1
    finally:
        signal.alarm(0)
    report["suppressed_calls"] = dict_count(guard.suppressed)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["overall"] = FAIL if any(s.status == FAIL for s in steps) else PASS
    write_report(report_path, {**report, "steps": [s.__dict__ for s in steps]})
    print(f"OVERALL {report['overall']}  report: {report_path}", flush=True)
    return exit_code or (1 if report["overall"] == FAIL else 0)


def dict_count(items: list[dict]) -> dict:
    out: dict[str, int] = {}
    for i in items:
        out[i["kind"]] = out.get(i["kind"], 0) + 1
    return out


def _fixture_get(rows: list[dict], query: str) -> list[dict]:
    """Minimal PostgREST filter emulation for the sandbox fixture (brief_type/brief_date eq, lt, order, limit)."""
    qs = dict(urllib.parse.parse_qsl(query))
    out = list(rows)
    for col in ("brief_type", "brief_date"):
        v = qs.get(col)
        if v and v.startswith("eq."):
            out = [r for r in out if str(r.get(col))[:10] == v[3:] or r.get(col) == v[3:]]
        elif v and v.startswith("lt."):
            out = [r for r in out if str(r.get(col))[:10] < v[3:]]
    order = qs.get("order", "")
    if order:
        col, _, direction = order.partition(".")
        out.sort(key=lambda r: str(r.get(col)), reverse=direction.startswith("desc"))
    if "limit" in qs:
        out = out[:int(qs["limit"])]
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    sys.exit(main())
