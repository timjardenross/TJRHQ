"""
Uptime Kuma webhook receiver — USS-TJR-MSN-0366 Stream 6.

Uptime Kuma (louislam/uptime-kuma, run via deploy/docker-compose.watchlist.yml)
is this mission's first-party direct-probe signal: unlike changedetection.io
(content diffing) or downdetector_adapter.py (third-party crowdsourced
report volume), it is the one adapter in this codebase whose signal is a
DIRECT up/down probe of the target itself — closest in spirit to a vendor's
own status feed, but independently observed rather than vendor-reported.

Wired the same way as changedetection_webhook.py, and feeding the SAME
collection entry point (collection_engine.py's per-source `collect()`
contract) via the same webhook_queue module, but under its own queue name
and its own IntelligenceItem phrasing so the two signal types stay
distinguishable in intelligence_events (see
intelligence.ingestion.uptime_kuma_adapter.UptimeKumaAdapter, which drains
this queue).

Uptime Kuma's default "Webhook" notification type POSTs a fixed JSON shape
(confirmed against the actual bundled source in the pulled image,
/app/server/notification-providers/webhook.js — no custom body template
needed, unlike changedetection.io's plain-text Apprise body):
    {"heartbeat": {...}, "monitor": {...}, "msg": "..."}
heartbeat.status: 1 = up, 0 = down, 2 = pending, 3 = maintenance.
This receiver only queues a signal for an actual state-defining beat
(up/down), not "pending" — matches Uptime Kuma's own "important" flag,
which it sets exactly on real state transitions (first beat after startup,
and any up<->down flip), so a signal here always means something genuinely
changed or newly resolved, not routine noise from every single heartbeat.

Run standalone: `python -m intelligence.watchlist.uptime_kuma_webhook`
(binds 0.0.0.0:8766 by default; override with KUMA_WEBHOOK_PORT).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from intelligence.watchlist import webhook_queue

log = logging.getLogger(__name__)

QUEUE_NAME = "uptime_kuma"
DEFAULT_PORT = 8766
WEBHOOK_PATH = "/webhook/uptime-kuma"

_STATUS_UP = 1
_STATUS_DOWN = 0


def normalise_payload(body: dict) -> Optional[dict]:
    """body is Uptime Kuma's own webhook.js payload:
    {"heartbeat": {...}, "monitor": {...}, "msg": "..."}. Returns a
    webhook_queue record, or None when there's no usable monitor URL, or
    the beat isn't an actual up/down state (fails safe — never queues a
    'pending'/'maintenance' beat as if it were a real transition, and
    never invents a monitor URL)."""
    heartbeat = body.get("heartbeat") or {}
    monitor = body.get("monitor") or {}

    monitor_url = monitor.get("url")
    if not monitor_url:
        return None

    status = heartbeat.get("status")
    if status not in (_STATUS_UP, _STATUS_DOWN):
        return None

    status_label = "UP" if status == _STATUS_UP else "DOWN"
    monitor_name = monitor.get("name") or monitor_url
    beat_msg = heartbeat.get("msg") or body.get("msg") or ""
    ping = heartbeat.get("ping")

    title = (
        f"Watchlist probe: {monitor_name} is {status_label} "
        f"(Uptime Kuma first-party direct probe)"
    )
    summary = (
        f"[Watchlist signal type: uptime-kuma-probe (independent first-party "
        f"direct up/down probe of the target itself, not a vendor "
        f"self-report and not crowdsourced)] Uptime Kuma's own direct probe "
        f"of {monitor_url} recorded a real status transition to {status_label}."
        + (f" Probe message: {beat_msg}." if beat_msg else "")
        + (f" Response time: {ping}ms." if ping is not None else "")
    )

    return {
        "source_url": monitor_url,
        "title": title,
        "summary": summary,
        "url": monitor_url,
        "monitor_id": monitor.get("id"),
        "status": status_label,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "signal_type": "uptime_kuma_probe",
    }


class _Handler(BaseHTTPRequestHandler):
    server_version = "TJRWatchlistUptimeKumaWebhook/1.0"

    def log_message(self, fmt, *args):  # noqa: A003 — stdlib override
        log.info("[uptime_kuma_webhook] %s", fmt % args)

    def do_POST(self):  # noqa: N802 — stdlib override
        if self.path != WEBHOOK_PATH:
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception as exc:
            log.warning("[uptime_kuma_webhook] non-JSON body: %s", exc)
            self.send_response(400)
            self.end_headers()
            return

        record = normalise_payload(body)
        if record is None:
            log.info(
                "[uptime_kuma_webhook] beat not an actionable up/down "
                "transition (or no monitor URL) — not queued: %r", body,
            )
            self.send_response(200)  # not an error — pending/maintenance beats are expected
            self.end_headers()
            return

        webhook_queue.append_signal(QUEUE_NAME, record)
        log.info(
            "[uptime_kuma_webhook] queued real %s probe signal for %s",
            record["status"], record["source_url"],
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def do_GET(self):  # noqa: N802 — stdlib override
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "queued": webhook_queue.peek_count(QUEUE_NAME),
            }).encode())
            return
        self.send_response(404)
        self.end_headers()


def run(port: int = DEFAULT_PORT) -> None:
    logging.basicConfig(level=logging.INFO)
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    log.info("[uptime_kuma_webhook] listening on 0.0.0.0:%d%s", port, WEBHOOK_PATH)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    import os
    run(int(os.environ.get("KUMA_WEBHOOK_PORT", DEFAULT_PORT)))
