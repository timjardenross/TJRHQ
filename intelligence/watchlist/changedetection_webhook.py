"""
changedetection.io webhook receiver — USS-TJR-MSN-0366 Stream 6.

changedetection.io (dgtlmoon/changedetection.io, run via
deploy/docker-compose.watchlist.yml) does its own persistent polling/diffing
of each watched page on its own schedule, entirely inside its container.
When it detects a real content change on a watch, it fires its own
notification system (Apprise) at whatever URL(s) that watch is configured
with. This process is that URL's target: a small stdlib-only HTTP server
(no new dependency — matches this codebase's existing adapters, which are
all plain `urllib`) that receives the real POST, normalises it into the
same shape `intelligence.ingestion.changedetection_adapter.ChangeDetectionAdapter`
expects, and hands it to `webhook_queue.append_signal()` — the same
collection entry point (collection_engine.py's per-source `collect()`
contract, exactly as `downdetector_adapter.py` and every other adapter use)
picks it up from there on the next collection cycle. This module never
touches intelligence_store.py directly and never fabricates an
IntelligenceItem itself — it only normalises and queues.

Wiring on the changedetection.io side (see deploy/docker-compose.watchlist.yml
and the mission's own knowledge record for the exact watch this was
configured against): each watch's Notification URL is
    json://host.docker.internal:8765/webhook/changedetection
and its Notification Body is the plain-text, pipe-delimited template built
by `_NOTIFICATION_BODY_TEMPLATE` below (kept here, not just in the UI, so
the parsing contract and the template that produces it never drift apart).
changedetection.io wraps whatever Title/Body a watch is configured with
inside Apprise's `json://` scheme envelope
({"version", "title", "message", "attachments", "type"} — confirmed against
the actual bundled Apprise source in the pulled image,
/usr/local/apprise/plugins/custom_json.py) — this receiver un-wraps that
envelope, then re-parses the pipe-delimited "message" field.

Run standalone: `python -m intelligence.watchlist.changedetection_webhook`
(binds 0.0.0.0:8765 by default; override with CD_WEBHOOK_PORT).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from intelligence.watchlist import webhook_queue

log = logging.getLogger(__name__)

QUEUE_NAME = "changedetection"
DEFAULT_PORT = 8765
WEBHOOK_PATH = "/webhook/changedetection"

# The exact template configured as this watch's Notification Body in
# changedetection.io's UI/API — see deploy/docker-compose.watchlist.yml's
# comment block for the curl/API call that sets this on the real watch.
# "~|~" is an arbitrary low-collision field separator (not a JSON structure)
# because changedetection.io's token substitution is plain string
# interpolation, not template-aware JSON escaping — asking it to emit valid
# embedded JSON directly risks a broken payload the moment a diff snippet
# contains a quote or backslash. Every field this receiver reads is listed
# here; add a field on both sides together if this ever needs to carry more.
NOTIFICATION_BODY_TEMPLATE = (
    "watch_uuid={{watch_uuid}}~|~"
    "watch_url={{watch_url}}~|~"
    "watch_title={{watch_title}}~|~"
    "diff_added={{diff_added}}~|~"
    "diff_removed={{diff_removed}}"
)
NOTIFICATION_TITLE_TEMPLATE = "changedetection.io: {{watch_url}}"

_FIELD_SEP = "~|~"


def parse_notification_message(message: str) -> dict:
    """Parse the pipe-delimited message body produced by
    NOTIFICATION_BODY_TEMPLATE above. Unknown/missing fields default to
    None rather than raising — a changedetection.io version bump that
    changes token behaviour should degrade to a thinner IntelligenceItem,
    not a dropped one silently swallowed by an exception."""
    fields: dict[str, Optional[str]] = {
        "watch_uuid": None, "watch_url": None, "watch_title": None,
        "diff_added": None, "diff_removed": None,
    }
    for part in message.split(_FIELD_SEP):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        if key in fields:
            fields[key] = value.strip()
    return fields


def normalise_payload(body: dict) -> Optional[dict]:
    """body is the already-JSON-decoded Apprise json:// envelope
    ({"title", "message", ...}). Returns a webhook_queue record, or None if
    the payload doesn't carry a usable watch_url (fails safe — never queues
    a signal with no source to attribute it to)."""
    message = body.get("message") or ""
    fields = parse_notification_message(message)
    watch_url = fields.get("watch_url")
    if not watch_url:
        return None

    watch_title = fields.get("watch_title") or watch_url
    diff_added = (fields.get("diff_added") or "").strip()
    diff_removed = (fields.get("diff_removed") or "").strip()

    title = (
        f"Watchlist change detected: {watch_title} — content change via "
        f"persistent diff-watch (changedetection.io)"
    )
    summary_parts = [
        f"[Watchlist signal type: changedetection-diff (persistent third-party "
        f"diff-watch, not a vendor self-report)] changedetection.io detected a "
        f"real content change on a watched page ({watch_url})."
    ]
    if diff_added:
        summary_parts.append(f"Added: {diff_added[:600]}")
    if diff_removed:
        summary_parts.append(f"Removed: {diff_removed[:600]}")
    summary = " ".join(summary_parts)

    return {
        "source_url": watch_url,
        "title": title,
        "summary": summary,
        "url": watch_url,
        "watch_uuid": fields.get("watch_uuid"),
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "signal_type": "changedetection_diff",
    }


class _Handler(BaseHTTPRequestHandler):
    server_version = "TJRWatchlistChangeDetectionWebhook/1.0"

    def log_message(self, fmt, *args):  # noqa: A003 — stdlib override
        log.info("[changedetection_webhook] %s", fmt % args)

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
            log.warning("[changedetection_webhook] non-JSON body: %s", exc)
            self.send_response(400)
            self.end_headers()
            return

        record = normalise_payload(body)
        if record is None:
            log.warning(
                "[changedetection_webhook] payload had no usable watch_url, "
                "not queued: %r", body,
            )
            self.send_response(422)
            self.end_headers()
            return

        webhook_queue.append_signal(QUEUE_NAME, record)
        log.info(
            "[changedetection_webhook] queued real change signal for %s",
            record["source_url"],
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
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)  # nosec B104 - must be reachable from the changedetection.io Docker container at host.docker.internal, which requires listening on all interfaces, not just loopback (see deploy/watchlist-changedetection-webhook.service and docker-compose.watchlist.yml) - reviewed 2026-09-12
    log.info("[changedetection_webhook] listening on 0.0.0.0:%d%s", port, WEBHOOK_PATH)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    import os
    run(int(os.environ.get("CD_WEBHOOK_PORT", DEFAULT_PORT)))
