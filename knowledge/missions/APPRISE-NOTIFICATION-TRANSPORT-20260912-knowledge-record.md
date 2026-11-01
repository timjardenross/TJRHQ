# Knowledge Record — Apprise notification transport, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0366 |
| Title | The code path was proven with a genuinely real send — the one thing that turned out fake-able was the network path to get there |
| Date | 2026-09-12 |
| Lesson | LL-163 |

## Outcome

Added `Transport.APPRISE` and `_send_apprise()` to
`core/platform/notification_service.py` (USS-TJR-MSN-0366 Stream 9) — a
structural hedge against a repeat of the 2026-09-08 Slack-retirement
migration this module's own header documents, where changing the active
transport meant deleting `_send_slack()` and rewiring `_SENDERS` by hand.
Apprise (https://github.com/caronc/apprise, `pip install apprise`, added
to `platform-runtime/requirements.txt` — checked via `pip install
--dry-run` first: zero pinned dependencies of its own, zero conflict with
this file's existing `anthropic`/`google-genai`/`openai` pins) is a single
library speaking 100+ notification-transport config-URL schemes. Reads
one or more from the `APPRISE_URLS` env var (comma-separated) and never
special-cases a URL's scheme/host inside `_send_apprise()` — the next
transport swap is `APPRISE_URLS="ntfy://…"` becoming
`APPRISE_URLS="discord://…"`, not a code change.

Matched the module's existing conventions rather than bolting on a
parallel path:
- `severity` now threads through `notify()` → `_send_one()` → every
  `_SENDERS` entry (both `_send_telegram()` and `_send_apprise()` accept
  it — Telegram ignores it, kept only for call-signature parity; Apprise
  maps it to its own `NotifyType` via `_SEVERITY_TO_APPRISE_TYPE`).
- Rendering is now transport-selected via a `_RENDERERS` dict
  (`Transport.TELEGRAM: _render`, `Transport.APPRISE: _render_for_apprise`),
  mirroring the existing `_SENDERS` dict shape exactly.
- `_render_for_apprise()` reuses the SAME `TEMPLATES`/`_RAW_TEMPLATES`
  registry `_render_full()` already renders from — no second, diverging
  template set — then strips the Telegram-only `<b>`/`<code>` HTML tags
  and un-escapes the `&amp;`/`&lt;`/`&gt;` entities `_escape_telegram_html`
  applied, since Apprise sends are plain text. Added `_SEVERITY_EMOJI` so
  the "plain" template (TEMPLATES' only entry with no built-in emoji)
  still carries an urgency cue on Apprise; "alert"/"info" already have
  one baked into `TEMPLATES`, "raw" (caller-composed) is left untouched
  either way.
- `NotificationResult.message_id` stays `None` for `Transport.APPRISE` by
  design, documented in the dataclass's own field comment: Apprise's
  fan-out `notify()` returns one bare bool across every config URL it
  holds, not a per-message id the way Telegram's `sendMessage` response
  carries one.
- Extended `core/platform/test_notification_service.py`'s existing
  `fake_telegram` fixture to accept the new `severity` parameter (it was
  a 3-arg fake; the sender interface is now 4-arg) and added 6 new tests
  covering the render-stripping, the emoji prefix, missing/invalid
  `APPRISE_URLS`, and `notify(transport=Transport.APPRISE)` routing. All
  14 tests (8 pre-existing + 6 new) pass.

**Real send, verified live** (see `NotificationResult`'s own docstring
convention on why a "verified" claim needs repeatable evidence — a
`message_id` for Telegram, this module's own `ok`/receiving-transport
record for Apprise, per this file's new field comment):

```
>>> import core.platform.notification_service as ns
>>> ns.notify(
...     "Apprise hedge test - USS-TJR-MSN-0366 Stream 9 - real end-to-end send",
...     title="TJR Notification Test", severity=ns.Severity.WARNING,
...     transport=ns.Transport.APPRISE, max_retries=0,
... )
NotificationResult(ok=True, transport=<Transport.APPRISE: 'apprise'>,
attempts=1, error=None, sent_at='2026-09-12T05:57:53.491687', message_id=None)
```

Polling the receiving topic's real JSON API immediately after
(`GET /<topic>/json?poll=1`, the exact ntfy-protocol verification
endpoint this task specified) returned the real message back:

```json
{"id": "local1789192673490", "time": 1789192673, "event": "message",
 "topic": "tjr-apprise-hedge-9f3k7q2x-20260912", "title": "",
 "message": "⚠️ Apprise hedge test - USS-TJR-MSN-0366 Stream 9 - real end-to-end send"}
```

`time: 1789192673` = `2026-09-12T05:57:53+00:00` UTC — matches
`NotificationResult.sent_at` to the second. A second real send using
`template="alert"` (title `"Engineering <Status>"`, body containing a
literal `&`) confirmed the HTML-stripping/unescaping path for real too —
the topic's history shows `"🚨 Engineering <Status>\nReactor coolant flow
nominal & stable"`: no `<b>` tag (stripped, per `_render_for_apprise`),
the literal `<Status>` preserved as plain text (never HTML-interpreted),
the `&` un-escaped back from `&amp;`, and no duplicate emoji (the
"alert" template's own 🚨 used, `_SEVERITY_EMOJI`'s prefix logic only
firing for "plain").

## Lesson

**The one real limitation hit**: this deployment's network egress policy
blocks the public `ntfy.sh` host itself. Confirmed directly, not assumed —
`ns.notify(..., transport=Transport.APPRISE)` with `APPRISE_URLS`
pointed at the real `ntfy://ntfy.sh/<topic>` returned a real
`NotificationResult(ok=False, error="apprise notify() returned False …")`,
and a bare `curl https://ntfy.sh/` independently confirmed the same
block (`CONNECT tunnel failed, response 403`) — as did `api.telegram.org`,
`discord.com`, `webhook.site`, `google.com`, and even `example.com`; only
`api.anthropic.com`, `pypi.org`/`files.pythonhosted.org`, and
`github.com`/`api.github.com` (for repos this session attached) are
reachable from inside this sandboxed session. This is an environment/
network-policy fact, not a defect in `_send_apprise()` — the function
correctly attempted the send, correctly reported the real failure, and
would succeed unmodified in a deployment whose egress policy allows the
target host (exactly the "swap the config string" property Apprise
exists to provide).

Given that, the "real send, verified live" evidence above was produced
against a small local stand-in
(`/tmp/…/scratchpad/local_ntfy_stub.py`, not committed to the repo — a
throwaway test fixture, not a shipped module) implementing ntfy's real,
publicly-documented publish/subscribe wire protocol (POST with a JSON
`{"topic", "message"}` body; `GET /<topic>/json?poll=1` → newline-
delimited JSON) closely enough that Apprise's own unmodified `NotifyNtfy`
plugin, over a real HTTP connection, sent to it and got back a real
response it accepted. The only unreal part of this evidence chain is
*which* server received the request — the real `ntfy` self-hosted/private
mode's HTTP behavior (confirmed via Apprise's own DEBUG logging: `ntfy
POST URL: http://<host>` with a JSON body, not the plain-text-in-path
form the "cloud" mode without an explicit host uses) is what the stand-in
had to match, and did, on the first attempt only after fixing a topic-
extraction bug caught by actually running the real round trip (the
stand-in initially read the topic from the URL path, but apprise's
private-mode payload puts it inside the JSON body instead — an assumption
that would have shipped wrong without a real send actually being tried).

The broader lesson: "prove it with a real send" and "the destination is
internet-reachable from this environment" are two separate claims, and a
sandboxed session's egress allowlist can falsify the second while the
implementation under test remains completely correct. Don't let a blocked
network path get treated as "couldn't verify" — attempt the real target
first (to get a real, honest failure on record, not a guess), then verify
the actual code path with the most-real substitute available, and say
plainly which parts of the evidence are which.

## Future Guidance

Before claiming an Apprise (or any outbound-HTTP) integration is "verified
live" from inside a sandboxed agent session, check the egress policy
first with a plain `curl` to the intended host — `curl -sS
http://127.0.0.1:38001/__agentproxy/status` after a failed attempt names
the exact rejection reason and lists recent blocked hosts. If the real
target is blocked, do not silently substitute a local stand-in without
saying so: attempt the real send (record the real, honest failure), then
build the closest available real substitute (a real protocol
implementation on localhost, not a hand-waved "trust me"), and label
every piece of evidence with which claim it actually supports. In an
unrestricted deployment, re-run the exact same `notify(...,
transport=Transport.APPRISE)` call against `APPRISE_URLS="ntfy://ntfy.sh/
<topic>"` before relying on this integration for a real alert — nothing
in `_send_apprise()` needs to change for that, but nothing here has
proven the public ntfy.sh host specifically works from a
network-unrestricted context, only that the code that would talk to it
is correct.
