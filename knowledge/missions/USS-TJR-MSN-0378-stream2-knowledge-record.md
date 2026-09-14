# Knowledge Record — USS-TJR-MSN-0378 (Stream 2 only)

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0378 |
| Title | Living Memory Across the Ship — Stream 2 (XO conversational turn memory) |
| Date | 2026-09-14 |
| Source | TJR HQ Capability Brief (2026-09-14), Play B. Cross-refs MEM-1 (rank 1/25), XO-1 (rank 3/25) |
| Commits | `616222b4b` (feature), `fe46d86f8` (docstring drift fix, filed under this mission but independent of Stream 2 itself) |

## Why this record is separate

Stream 2 is explicitly the standalone, low-risk piece of MSN-0378 — it does
not depend on Streams 1/3/4/5/6 and ships independently. Per the mission's
own Reporting instruction, it gets its own knowledge record rather than
waiting for the rest of the (larger, still-open) consolidation arc.

## Pre-flight verification (carried out before any code change)

- `grep -rln "unified_memory" --include=*.py .` — confirmed the mission
  brief's file list exactly: 7 files (not 6 — `episodic_memory.py` was
  correctly counted).
- `grep -n "from core.platform.unified_memory import" platform-runtime/lib/officers/daily_operations_cycle.py`
  — confirmed line 126, `from core.platform.unified_memory import MemoryType, recall`,
  a real live import.
- `grep -n "conversation_turns|chat_history|conversation_history" telegram-bots/xo/app.py`
  — zero matches, confirmed. No turn-replay mechanism existed anywhere in
  XO's live code path.
- unified_memory.py's docstring claim "Standalone module. Not yet adopted
  by any existing caller" — confirmed **false** against current repo state
  (daily_operations_cycle.py is a real caller). Fixed separately in
  `fe46d86f8` (docstring only, no behavior change) — this closes the
  Pre-flight item 2 drift called out in the mission brief's Acceptance
  criteria.

## What shipped

- **Migration** `core/infrastructure/supabase/migrations/0208_conversation_turns.sql`
  — new `conversation_turns` table (chat_id, role, text, created_at,
  consolidated_at), row-per-turn (not a JSON blob column, unlike
  `debrief_sessions.turns`) because this table is read as a sliding
  time/count window across an open-ended chat, not as one whole unit per
  short-lived session. RLS: service_role write, authenticated read — same
  convention as `debrief_sessions`/`alert_silences` (migrations 0206/0205).
  Applied live to Supabase project `cjvrpjwewsrumnbdydgg` (USSTJR).
- **`telegram-bots/xo/app.py`** — `_log_conversation_turn()` (best-effort
  insert, never raises into the reply path) and `_get_recent_turns()` (last
  10 turns / 120 minutes, whichever binds first) wired into `cmd_message`'s
  plain-LLM-reply branch (the only path with no other handled intent).
  `_xo_system_prompt()` gained a `recent_turns` param, appended after the
  open-missions block.
- **Service restart**: `tg-xo.service` restarted to load the change;
  confirmed `active (running)` post-restart.
- `consolidated_at` column added now (nullable, unused) so Stream 5's
  nightly consolidation job has a marker to claim rows without deleting
  raw history — anticipates that stream without building it.

## Acceptance status

- "Stream 2 ships independently and is verifiably live in XO" — **shipped
  and live**, but **not yet verified against a real multi-turn Telegram
  exchange** — this session has no Telegram session as the Captain to
  drive that check. `select count(*) from conversation_turns` reads 0 rows
  as of this record (expected: no Captain messages sent since the
  restart). **Needs a real follow-up check**: next time the Captain sends
  XO two or more messages in one sitting, confirm (a) both turns land in
  `conversation_turns`, and (b) XO's reply demonstrably references
  earlier-turn content, not just live DB state.

## Explicitly not touched by this stream

Long-term extraction into Graphiti (Stream 5), the vector-store
consolidation (Stream 3), and `unified_memory.py`'s SEMANTIC/FACTUAL
backend repoint (Stream 4) are all still open — this record covers Stream
2 only. See the forthcoming combined Streams 1+3+4+5+6 record for the rest
of the mission's status.
