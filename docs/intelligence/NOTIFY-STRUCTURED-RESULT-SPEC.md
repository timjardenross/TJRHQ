# Structured send result for `notify` (specification for Production Operations)

Status: IMPLEMENTED as an additive, opt-in change in `core/platform/notification_service.py` (see "As implemented" at the end; the
Proposed contract below is kept for provenance and the implementation differs in naming). `intelligence/delivery_adapter.py` implements the contract below on top of the current `notify`, so the
brief delivery record works today and can switch to a native implementation later without changing its callers.

## What the current `notify` cannot tell a caller
1. `notify(chunk=True)` returns the result of the LAST chunk only. If an earlier chunk was rejected and the last was
   accepted, the single result says `ok=True`.
2. After a failed chunk the loop continues with the next chunk (out-of-order or partial delivery, reported as ok).
3. Per-chunk `message_id`s are discarded, so nothing durable can say which parts reached the chat.
4. The internal retry (`max_retries=1` default) re-sends after any non-permanent failure, including a timeout after
   the request was written. The first request may already have been delivered, so this can duplicate silently.
5. There is no way to distinguish "provider rejected it" from "outcome unknown".

(Items 1, 2 and 4 are demonstrated against the real function with a faked sender in
`tests/test_wp2_delivery_adapter_and_brief.py`.)

## Proposed contract
```python
@dataclass
class ChunkSend:
    index: int; total: int
    state: Literal["CONFIRMED", "FAILED", "UNKNOWN", "NOT_ATTEMPTED"]
    message_id: int | None      # only when CONFIRMED
    error: str | None           # short, capped, no request body, no credential
    attempts: int
    sent_at: str | None

@dataclass
class NotificationDetail:       # returned by notify(..., detail=True); legacy callers keep NotificationResult
    chunks: list[ChunkSend]
    ok: bool                    # True only if every chunk is CONFIRMED
```
Rules: `chunk_stop_on_failure=True` option (stop at the first chunk that is FAILED or UNKNOWN; later chunks
NOT_ATTEMPTED). Retries only for definite non-delivery; never after UNKNOWN. Default behaviour of existing callers
is unchanged unless they opt in.

### Classification (what the adapter does today)
| Provider/transport signal | State | Retry |
|---|---|---|
| `ok` from the Bot API response | CONFIRMED (with `message_id`) | no |
| HTTP 400, 401, 403, 404 | FAILED | no |
| HTTP 429 | FAILED | once, after backoff |
| missing token/chat id; connection refused; DNS failure; network unreachable | FAILED | no |
| timeout, connection reset or closed, HTTP 5xx, unparseable or empty error | UNKNOWN | never |

Anything not provably undelivered is UNKNOWN. The Telegram Bot API cannot list sent messages, so UNKNOWN cannot be
reconciled by lookup: it is recorded UNCONFIRMED and handled by the single marked recovery resend policy.
This is a provider limitation and is not presented as reconciliation.

## Open questions for Production Operations
- Native `detail=True` (or a new function) vs keeping the adapter.
- Whether `_split_html_aware` may be treated as a public helper (the adapter imports it so boundaries match today's).
- Whether the scheduler wants to call the interrupted-delivery recovery pass (`delivery_record.recover_interrupted` then
  `plan_recovery`) at start-up; scheduler wiring is theirs and is not part of this change.

## As implemented (additive, default off)
`notify(..., strict: bool = False, chunk_stop_on_failure: bool | None = None)`; with `strict=False` (the default) every
behaviour is byte-for-byte the previous one (proved by golden tests against a copy of the previous module).

* `NotificationResult` gains two optional fields at the end: `chunk_results: list[ChunkResult] | None` and
  `delivery_outcome: str | None`. Both are `None` unless `strict=True`. Existing positional and keyword construction is unchanged.
* `ChunkResult(index, total, state, attempts, message_id, error, sent_at, note)`; `state` is `CONFIRMED`, `FAILED`,
  `UNKNOWN` or `NOT_ATTEMPTED`. `error` is capped at 200 characters; `note="confirmed_without_message_id"` flags a Telegram
  acceptance that carried no message id.
* `delivery_outcome`: `CONFIRMED` (every chunk confirmed), `PARTIAL` (some confirmed, not all, including an unconfirmed or
  not-attempted remainder), `FAILED` (none confirmed, none ambiguous), `UNKNOWN` (none confirmed, at least one ambiguous).
  This is the same rule as `delivery_record.outcome_from_chunks` (tested over every state combination).
* `.ok` keeps its legacy meaning in every mode: the result of the LAST chunk attempted. Strict callers must read
  `delivery_outcome`, never `.ok`, to decide whether a multi-chunk body was delivered. `.attempts`, `.error`, `.message_id`
  and `.sent_at` are those of the last chunk attempted, as before.
* Strict mode never retries an ambiguous failure (timeout or connection loss after the request may have been accepted,
  HTTP 5xx, unparseable reply, a sender that raises). It retries (up to `max_retries`) only definite non-delivery that is safe
  to repeat: HTTP 429, connection refused, DNS failure, network unreachable. HTTP 400/401/403/404 and missing configuration are
  definite and not retried. Classification is `classify_send_error(error) -> (state, retry_safe)`, shared with
  `intelligence/delivery_adapter.py`.
* `chunk_stop_on_failure` (strict only, default True): stop at the first chunk that is FAILED or UNKNOWN; later chunks are
  `NOT_ATTEMPTED` and nothing is sent for them. `False` continues (legacy ordering) while still reporting per-chunk truth.
* `_CALL_LOG` gets one entry per chunk actually attempted, as today.
* `intelligence/delivery_adapter.chunks_from_notification(result)` maps a strict result onto `delivery_record.ChunkResult`s.
  The brief delivery path keeps calling one piece at a time with `max_retries=0` (equivalent safety, no dependency on the
  new parameter during a deploy skew).

### Default-behaviour duplicate risk (a decision for Production Operations)
With the default `max_retries=1`, a legacy `notify()` call whose first request timed out AFTER Telegram accepted it sends the
message again. This is unchanged by this work and applies to every caller that does not pass `strict=True`. A change of the
default (for example `max_retries=0` for ambiguous errors only) would alter Telegram-visible behaviour for every bot and is
not made here. Measuring it needs only the existing log lines (`send failed after 2 attempt(s)` with a timeout error, then a
later accepted message); no code change is required to count occurrences.
