#!/usr/bin/env python3
"""Telegram Chief Engineer agent — entry point (long-polling).

Captain TJR chats with the agent directly. It reasons over read-only system
context and logs append-only build requests. An allowlist gate ensures only the
Captain's chat id(s) are served; everyone else is politely refused.

Boundaries enforced elsewhere: read-only context (context_reader), restricted
Supabase (supabase_readonly), append-only logging (build_request).
"""

from __future__ import annotations

import logging
import sys

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [telegram-engineer] %(levelname)s %(message)s",
)
log = logging.getLogger("telegram-engineer")


def _build_supabase_client():
    try:
        import supabase_readonly
        client = supabase_readonly.get_client_or_none()
        if client is None:
            log.warning("Supabase not configured — running with filesystem context only.")
        return client
    except Exception as exc:
        log.warning("Supabase client unavailable (%s) — filesystem context only.", exc)
        return None


def main() -> int:
    missing = config.validate_runtime()
    if missing:
        log.error("Missing required env: %s", ", ".join(missing))
        log.error("Fill telegram-bot/.env (see .env.example) and restart.")
        return 1

    try:
        from telegram import (
            BotCommand,
            BotCommandScopeAllGroupChats,
            BotCommandScopeAllPrivateChats,
            InlineKeyboardButton,
            InlineKeyboardMarkup,
            Update,
        )
        from telegram.ext import (
            Application,
            CallbackQueryHandler,
            CommandHandler,
            ContextTypes,
            MessageHandler,
            filters,
        )
    except Exception as exc:
        log.error("python-telegram-bot not installed (%s). Run: pip install -r requirements.txt", exc)
        return 1

    import agent
    import asyncio
    import eng_operator
    from approval import ApprovalError, submit_approval
    from build_request import log_build_request

    supabase_client = _build_supabase_client()
    allowed = config.allowed_chat_ids()
    log.info("Allowlist active for %d chat id(s).", len(allowed))

    # Remembers the most recent /build request per chat so the inline "Approve"
    # button can act on it without stuffing the (long) request id into Telegram's
    # 64-byte callback_data budget.
    _last_build_request: dict[int, str] = {}

    # Directed Engineering Operator: one pending (Approve-gated) mutation per chat.
    _eng_pending = eng_operator.PendingStore()

    # --- guard ------------------------------------------------------------
    def _gate(update: "Update") -> int | None:
        chat = update.effective_chat
        chat_id = chat.id if chat else None
        if not config.is_allowed(chat_id):
            log.warning("Refused chat_id=%s (not in allowlist).", chat_id)
            return None
        return chat_id

    REFUSAL = "🚫 This is Captain TJR's private Chief Engineer channel. Access denied."

    # --- handlers ---------------------------------------------------------
    async def cmd_start(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        await update.message.reply_text(
            "🖖 Chief Engineer online.\n"
            "Ask me about ship systems — missions, ADRs, build records, risks. I read "
            "the ship's records read-only and can log a *build request* for governance "
            "triage.\n\n"
            "Commands: /build <note> — log a build request from our chat • "
            "/approve <id> — approve it and auto-engineer (review-only) • "
            "/context — show what I can see • /reset — clear our thread • /help",
            parse_mode="Markdown",
        )

    async def cmd_help(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        await update.message.reply_text(
            "I am read-only. I never change code, commit, restart services, or mutate "
            "mission status. The only thing I create is an append-only build request "
            "(PENDING_TRIAGE) for Number One / XO to triage.\n\n"
            "/build <optional note> — summarise our conversation into a structured "
            "build request and log it.\n"
            "/approve <id> — approve a logged build request; a privileged executor "
            "then auto-generates a review-only patch / draft PR (nothing is merged). "
            "You can also tap the Approve button under a /build.\n"
            "/context — list visible context sources.\n"
            "/reset — start a fresh thread."
        )

    async def cmd_context(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        import context_reader
        lines = [
            f"• {s['label']} ({s['path']}): {s['files']} file(s)"
            for s in context_reader.list_sources()
        ]
        sb = "connected" if supabase_client is not None else "filesystem-only"
        await update.message.reply_text("Visible read-only context:\n" + "\n".join(lines) + f"\n\nSupabase: {sb}")

    async def cmd_reset(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        agent.reset(chat_id)
        await update.message.reply_text("🧹 Thread cleared.")

    async def cmd_build(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        note = " ".join(ctx.args) if ctx.args else ""
        await update.message.reply_text("📝 Drafting a build request from our conversation…")
        user = update.effective_user
        requested_by = f"@{user.username}" if user and user.username else f"tg:{chat_id}"
        try:
            req = agent.draft_build_request(chat_id, note, requested_by)
            result = log_build_request(req, supabase_client=supabase_client)
        except Exception as exc:
            log.exception("build request failed")
            await update.message.reply_text(f"⚠️ Could not log build request: {exc}")
            return
        sb = "✅ logged" if result.supabase_ok else f"⚠️ skipped ({result.supabase_error or 'no DB'})"
        _last_build_request[chat_id] = result.request_id
        # The approve button (and the executor) only work if the row reached the
        # DB — the executor polls Supabase, not the markdown file.
        if result.supabase_ok:
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("✅ Approve & Build", callback_data="approve_last")]]
            )
            approve_hint = (
                "\n\nApprove to auto-engineer (review-only draft PR): tap the button "
                f"below or send `/approve {result.request_id}`."
            )
        else:
            markup = None
            approve_hint = (
                "\n\n⚠️ Not in the DB, so it can't be auto-approved yet "
                "(the executor reads Supabase)."
            )
        await update.message.reply_text(
            f"✅ Build request logged as *PENDING_TRIAGE*.\n"
            f"ID: `{result.request_id}`\nFile: `{result.file_path}`\nSupabase: {sb}\n\n"
            f"*{req.title}*\n{req.summary}{approve_hint}",
            parse_mode="Markdown",
            reply_markup=markup,
        )

    async def _do_approval(chat_id: int, request_id: str) -> str:
        """Shared approval path for the command and the inline button. Returns a
        user-facing status string (never raises)."""
        try:
            marker_id = submit_approval(request_id, chat_id, supabase_client)
        except ApprovalError as exc:
            return f"⚠️ {exc}"
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("approval failed")
            return f"⚠️ Could not log approval: {exc}"
        return (
            f"✅ *Approved.* Engineering will run automatically (review-only).\n"
            f"Request: `{request_id}`\nApproval marker: `{marker_id}`\n\n"
            "I'll message here when the patch/draft PR is ready."
        )

    async def cmd_approve(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        request_id = (ctx.args[0].strip() if ctx.args else "") or _last_build_request.get(chat_id, "")
        if not request_id:
            await update.message.reply_text(
                "Usage: `/approve <request_id>` (or tap Approve under a /build).",
                parse_mode="Markdown",
            )
            return
        msg = await _do_approval(chat_id, request_id)
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def on_approve_callback(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        query = update.callback_query
        chat = update.effective_chat
        chat_id = chat.id if chat else None
        if not config.is_allowed(chat_id):
            await query.answer("Access denied.", show_alert=True)
            return
        await query.answer("Approving…")
        request_id = _last_build_request.get(chat_id, "")
        if not request_id:
            await query.edit_message_reply_markup(reply_markup=None)
            await ctx.bot.send_message(
                chat_id=chat_id,
                text="⚠️ I lost track of which build to approve — send `/approve <id>`.",
                parse_mode="Markdown",
            )
            return
        msg = await _do_approval(chat_id, request_id)
        # Drop the button so it can't be tapped twice.
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:  # noqa: BLE001 - editing markup is best-effort
            pass
        await ctx.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

    async def on_message(update: "Update", ctx: "ContextTypes.DEFAULT_TYPE") -> None:
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        text = (update.message.text or "").strip()
        if not text:
            return
        await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
        reply = agent.answer(chat_id, text, supabase_client=supabase_client)
        # Telegram hard limit is 4096 chars.
        await update.message.reply_text(reply[:4000])

    # --- read-only info commands (parity with the XO; reuse its action handlers) ---
    async def _send_xo_action(update, ctx, name, args):
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        import asyncio
        from pathlib import Path
        await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

        def _call():
            xo_dir = str(Path(__file__).resolve().parent.parent / "xo-bot")
            if xo_dir not in sys.path:
                sys.path.append(xo_dir)
            import actions as xo_actions
            fn = xo_actions.ACTIONS.get(name)
            return fn(args) if fn else (False, f"unknown action {name}")

        loop = asyncio.get_event_loop()
        ok, out = await loop.run_in_executor(None, _call)
        await ctx.bot.send_message(chat_id=chat_id, text=(out or "(no result)")[:4000])

    async def cmd_missions(update, ctx):
        await _send_xo_action(update, ctx, "list_missions", {"status": " ".join(ctx.args)})

    async def cmd_search(update, ctx):
        if _gate(update) is None:
            await update.message.reply_text(REFUSAL)
            return
        q = " ".join(ctx.args).strip()
        if not q:
            await update.message.reply_text("Usage: /search <text>")
            return
        await _send_xo_action(update, ctx, "search_memory", {"query": q})

    async def cmd_status(update, ctx):
        await _send_xo_action(update, ctx, "delivery_status", {})

    async def cmd_note(update, ctx):
        """Capture a quick intelligence note into the Captain's Notebook."""
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        raw = " ".join(ctx.args).strip() if ctx.args else ""
        if not raw:
            await update.message.reply_text(
                "Usage: `/note <content>` — captures a note to the Captain's Notebook (CAPTURED status).\n"
                "Example: `/note Explore Starfleet API for mission sync`",
                parse_mode="Markdown",
            )
            return
        import notebook_writer
        note_id = notebook_writer.capture_note(raw_content=raw, source="telegram")
        if note_id:
            await update.message.reply_text(
                f"📓 Note captured — `{note_id[:8]}…`\n"
                "_Officer review will begin in the next pipeline cycle._",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "⚠️ Note capture failed — Supabase may be unavailable. "
                "Try again or use the portal."
            )

    # --- Advisory Runtime (MSN-0092) -------------------------------------
    def _advisory_mod(name: str):
        import sys as _sys
        from pathlib import Path as _Path
        _adv = _Path(__file__).resolve().parents[1] / "core" / "advisory"
        if str(_adv) not in _sys.path:
            _sys.path.insert(0, str(_adv))
        return __import__(name)

    def _advisory_text(action: str, query: str) -> str:
        """Run the shared advisory runtime (sync) and return markdown."""
        _svc = _advisory_mod("service")
        if action == "lessons":
            return _advisory_mod("lessons").to_markdown(_svc.invoke("lessons", query))
        if action == "evidence":
            brief = _svc.invoke("evidence", query)
            lines = [f"EVIDENCE — {query}", "", brief.get("narrative", "")]
            for d in brief.get("related_decisions", []):
                tag = f" [{d.get('outcome')}]" if d.get("outcome") else ""
                lines.append(f"- {d.get('decision_id')}{tag}: {d.get('question')}")
            for l in brief.get("lessons", []):
                lines.append(f"- {l.get('lesson_id')}: {l.get('title')}")
            return "\n".join(lines)
        if action == "metrics":
            return _advisory_mod("metrics").to_markdown()
        if action == "proactive":
            return _advisory_mod("proactive").to_markdown()
        if action == "intel":
            views = {"brief": "daily_brief", "picture": "operating_picture", "wellness": "wellness",
                     "strategic": "strategic", "forecast": "forecast", "trust": "data_quality",
                     "data": "data_quality"}
            view = (query or "brief").split()[0].lower() if query else "brief"
            mod = views.get(view, "daily_brief")
            return _advisory_mod(mod).to_markdown()
        if action == "awareness":
            prods = {"awareness": "daily_awareness_brief", "picture": "captains_operating_picture",
                     "resilience": "operational_resilience_watch", "wellness": "wellness_insights",
                     "strategic": "strategic_outlook", "opportunity": "opportunity_review"}
            view = (query or "awareness").split()[0].lower() if query else "awareness"
            fn = prods.get(view, "daily_awareness_brief")
            return _advisory_mod("presentation").to_markdown(getattr(_advisory_mod("products"), fn)())
        if action == "products":
            return _advisory_mod("products").catalogue_markdown()
        if action == "timeline":
            temporal = _advisory_mod("temporal")
            if not query:
                return temporal.to_markdown(temporal.what_changed())
            ql = query.lower()
            if "preced" in ql or "before" in ql:
                res = temporal.what_preceded(query)
            elif "begin" in ql or "start" in ql or "when" in ql:
                res = temporal.when_did_begin(query)
            elif "next" in ql or "happens" in ql or "usually" in ql:
                res = temporal.what_happens_next(query)
            else:
                res = temporal.what_changed(query) if "chang" in ql else temporal.what_preceded(query)
            return temporal.to_markdown(res)
        return _svc.invoke(action, query).to_markdown()

    def _advisory_outcome_text(args: list[str]) -> str:
        if len(args) < 2:
            return ("Usage: /advisory_outcome <advisory_id|last> <success|failure|partial> [note]")
        outcomes = _advisory_mod("outcomes")
        res = outcomes.record_outcome(args[0], outcome=args[1].lower(), feedback=" ".join(args[2:]))
        return ("✅ " if res.get("ok") else "⚠️ ") + str(res.get("message"))

    async def cmd_advisor(update, ctx):
        """/advisor <question> — multi-officer, evidence-based advisory."""
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        q = " ".join(ctx.args).strip()
        if not q:
            await update.message.reply_text("Usage: `/advisor <question>`", parse_mode="Markdown")
            return
        await update.message.reply_text("🧭 Consulting officers…")
        text = await _run_blocking(_advisory_text, "advice", q)
        await _send_long(chat_id, text)

    async def cmd_challenge(update, ctx):
        """/challenge <question> — advisory with red-team review surfaced."""
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        q = " ".join(ctx.args).strip()
        if not q:
            await update.message.reply_text("Usage: `/challenge <question>`", parse_mode="Markdown")
            return
        await update.message.reply_text("🔍 Running red-team review…")
        text = await _run_blocking(_advisory_text, "challenge", q)
        await _send_long(chat_id, text)

    async def cmd_lessons(update, ctx):
        """/lessons <topic> — prior lessons: what happened, what to avoid."""
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        q = " ".join(ctx.args).strip()
        if not q:
            await update.message.reply_text("Usage: `/lessons <topic>`", parse_mode="Markdown")
            return
        text = await _run_blocking(_advisory_text, "lessons", q)
        await _send_long(chat_id, text)

    async def cmd_evidence(update, ctx):
        """/evidence <question> — historical evidence + related prior decisions."""
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        q = " ".join(ctx.args).strip()
        if not q:
            await update.message.reply_text("Usage: `/evidence <question>`", parse_mode="Markdown")
            return
        text = await _run_blocking(_advisory_text, "evidence", q)
        await _send_long(chat_id, text)

    async def cmd_advisory_outcome(update, ctx):
        """/advisory_outcome <id|last> <success|failure|partial> [note] — close the loop."""
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        text = await _run_blocking(_advisory_outcome_text, list(ctx.args))
        await update.message.reply_text(text)

    async def cmd_advisor_metrics(update, ctx):
        """/advisor_metrics — advisory utilisation, success rates, top advisors."""
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        text = await _run_blocking(_advisory_text, "metrics", "")
        await _send_long(chat_id, text)

    async def cmd_advisor_scan(update, ctx):
        """/advisor_scan — proactive scan: what the system noticed (informational)."""
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        await update.message.reply_text("🛰 Scanning for emerging signals…")
        text = await _run_blocking(_advisory_text, "proactive", "")
        await _send_long(chat_id, text)

    async def cmd_timeline(update, ctx):
        """/timeline <question> — temporal query (what changed / preceded / began / next)."""
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        q = " ".join(ctx.args).strip()
        text = await _run_blocking(_advisory_text, "timeline", q)
        await _send_long(chat_id, text)

    async def cmd_intel(update, ctx):
        """/intel [brief|picture|wellness|strategic|forecast|trust] — intelligence views."""
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        q = " ".join(ctx.args).strip()
        text = await _run_blocking(_advisory_text, "intel", q)
        await _send_long(chat_id, text)

    async def cmd_awareness(update, ctx):
        """/awareness [product] — Daily Awareness Brief (meaning, not machinery)."""
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        q = " ".join(ctx.args).strip()
        text = await _run_blocking(_advisory_text, "awareness", q)
        await _send_long(chat_id, text)

    async def cmd_products(update, ctx):
        """/products — the intelligence product catalogue."""
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL)
            return
        text = await _run_blocking(_advisory_text, "products", "")
        await _send_long(chat_id, text)

    # --- Directed Engineering Operator (/eng_*) ---------------------------
    # Read commands run immediately; mutating commands stage a PendingAction and
    # only execute on an explicit Approve tap. GLM calls run in a thread so they
    # never block the poller.
    _ENG_KEYBOARD = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data="eng_approve"),
        InlineKeyboardButton("✖️ Cancel", callback_data="eng_cancel"),
    ]])

    async def _run_blocking(fn, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(*args))

    async def _send_long(chat_id: int, text: str) -> None:
        """Send text in <=4000-char chunks; prefer Markdown, fall back to plain
        so unpredictable model output can never 400 the bot."""
        for i in range(0, len(text), 4000):
            chunk = text[i:i + 4000]
            try:
                await app.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="Markdown")
            except Exception:
                await app.bot.send_message(chat_id=chat_id, text=chunk)

    def _eng_by(update, chat_id: int) -> str:
        u = update.effective_user
        return f"@{u.username}" if u and u.username else f"tg:{chat_id}"

    def _eng_arg(ctx) -> str:
        return ctx.args[0].strip() if ctx.args else ""

    async def cmd_eng_missions(update, ctx):
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL); return
        out = await _run_blocking(eng_operator.cmd_missions)
        await _send_long(chat_id, out)

    async def cmd_eng_pickup(update, ctx):
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL); return
        mid = _eng_arg(ctx)
        if not mid:
            await update.message.reply_text("Usage: `/eng_pickup <mission_id>`", parse_mode="Markdown"); return
        out = await _run_blocking(eng_operator.cmd_pickup, mid)
        await _send_long(chat_id, out)

    async def cmd_eng_plan(update, ctx):
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL); return
        mid = _eng_arg(ctx)
        if not mid:
            await update.message.reply_text("Usage: `/eng_plan <mission_id>`", parse_mode="Markdown"); return
        await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
        await update.message.reply_text(f"🧭 Generating GLM-5.2 engineering plan for `{mid}`…", parse_mode="Markdown")
        out = await _run_blocking(eng_operator.cmd_plan, mid)
        await _send_long(chat_id, out)

    async def cmd_eng_review(update, ctx):
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL); return
        mid = _eng_arg(ctx)
        if not mid:
            await update.message.reply_text("Usage: `/eng_review <mission_id>`", parse_mode="Markdown"); return
        await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
        await update.message.reply_text(f"🔎 Reviewing `{mid}` with GLM-5.2…", parse_mode="Markdown")
        out = await _run_blocking(eng_operator.cmd_review, mid)
        await _send_long(chat_id, out)

    async def _stage_and_prompt(update, chat_id, stage_result):
        """Stage a mutation and show the Approve/Cancel gate (or report a refusal)."""
        summary, action = stage_result
        if action is None:
            await _send_long(chat_id, summary)
            return
        _eng_pending.stage(chat_id, action)
        text = summary[:3800] + "\n\n*Approve to write this — nothing is changed until you do.*"
        try:
            await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=_ENG_KEYBOARD)
        except Exception:
            await app.bot.send_message(chat_id=chat_id, text=summary[:3800] + "\n\nApprove to write this.", reply_markup=_ENG_KEYBOARD)

    async def cmd_eng_status(update, ctx):
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL); return
        if len(ctx.args) < 2:
            await update.message.reply_text(
                "Usage: `/eng_status <mission_id> <status>`\n"
                "Status: Pending Triage · Assigned · In Progress · Awaiting Review · Completed",
                parse_mode="Markdown"); return
        mid = ctx.args[0].strip()
        status_text = " ".join(ctx.args[1:])
        res = await _run_blocking(eng_operator.stage_status, mid, status_text, _eng_by(update, chat_id))
        await _stage_and_prompt(update, chat_id, res)

    async def cmd_eng_log(update, ctx):
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL); return
        if len(ctx.args) < 2:
            await update.message.reply_text("Usage: `/eng_log <mission_id> <note>`", parse_mode="Markdown"); return
        mid = ctx.args[0].strip()
        note = " ".join(ctx.args[1:])
        res = await _run_blocking(eng_operator.stage_log, mid, note, _eng_by(update, chat_id))
        await _stage_and_prompt(update, chat_id, res)

    async def cmd_eng_handoff(update, ctx):
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL); return
        mid = _eng_arg(ctx)
        if not mid:
            await update.message.reply_text("Usage: `/eng_handoff <mission_id>`", parse_mode="Markdown"); return
        res = await _run_blocking(eng_operator.stage_handoff, mid, _eng_by(update, chat_id))
        await _stage_and_prompt(update, chat_id, res)

    async def cmd_eng_patch(update, ctx):
        chat_id = _gate(update)
        if chat_id is None:
            await update.message.reply_text(REFUSAL); return
        mid = _eng_arg(ctx)
        if not mid:
            await update.message.reply_text("Usage: `/eng_patch <mission_id>`", parse_mode="Markdown"); return
        await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")
        await update.message.reply_text(f"🩹 Generating a review-only patch proposal for `{mid}` (GLM-5.2)…", parse_mode="Markdown")
        res = await _run_blocking(eng_operator.stage_patch, mid, _eng_by(update, chat_id))
        await _stage_and_prompt(update, chat_id, res)

    async def on_eng_callback(update, ctx):
        query = update.callback_query
        chat = update.effective_chat
        chat_id = chat.id if chat else None
        if not config.is_allowed(chat_id):
            await query.answer("Access denied.", show_alert=True); return
        data = query.data
        action = _eng_pending.take(chat_id)
        try:
            await query.edit_message_reply_markup(reply_markup=None)  # one-shot button
        except Exception:
            pass
        if data == "eng_cancel":
            await query.answer("Cancelled.")
            await ctx.bot.send_message(chat_id=chat_id, text="✖️ Cancelled — nothing was written.")
            return
        if action is None:
            await query.answer("Nothing pending.")
            await ctx.bot.send_message(chat_id=chat_id, text="⚠️ I lost track of the pending action — re-issue the command.")
            return
        await query.answer("Applying…")
        result = await _run_blocking(eng_operator.apply_action, action)
        await _send_long(chat_id, result)

    # Menu last synced: 2026-06-21. Keep in lockstep with add_handler() calls below.
    _MENU = [
        ("missions", "List missions (optional status): /missions [status]"),
        ("status", "Delivery status — what's stuck and who owns it"),
        ("build", "Draft a build request from our chat: /build <note>"),
        ("approve", "Approve a build request: /approve <id>"),
        ("note", "Capture an intelligence note: /note <content>"),
        ("advisor", "Multi-officer advisory: /advisor <question>"),
        ("challenge", "Red-team a decision: /challenge <question>"),
        ("lessons", "Prior lessons on a topic: /lessons <topic>"),
        ("evidence", "Historical evidence + prior decisions: /evidence <question>"),
        ("advisory_outcome", "Close the loop: /advisory_outcome <id|last> <success|failure|partial>"),
        ("advisor_metrics", "Advisory metrics and top advisors"),
        ("advisor_scan", "Proactive scan — what the system noticed"),
        ("timeline", "Temporal query: /timeline <what changed / preceded / began / next>"),
        ("intel", "Intelligence views: /intel [brief|picture|wellness|strategic|forecast|trust]"),
        ("awareness", "Daily Awareness Brief: /awareness [product]"),
        ("products", "Intelligence product catalogue"),
        ("search", "Search Command Memory + mission files: /search <text>"),
        ("context", "Show the engineering context I'm working from"),
        ("reset", "Clear our conversation history"),
        ("help", "How the Chief Engineer works"),
        ("eng_missions", "Engineering: list engineering-actionable missions"),
        ("eng_pickup", "Engineering: load a mission's context: /eng_pickup <id>"),
        ("eng_plan", "Engineering: generate an implementation plan: /eng_plan <id>"),
        ("eng_patch", "Engineering: generate a review-only patch proposal: /eng_patch <id>"),
        ("eng_review", "Engineering: review work vs acceptance criteria: /eng_review <id>"),
        ("eng_status", "Engineering: set lifecycle status: /eng_status <id> <status>"),
        ("eng_handoff", "Engineering: emit a Claude-Code handoff: /eng_handoff <id>"),
        ("eng_log", "Engineering: append a progress note: /eng_log <id> <note>"),
    ]

    async def _post_init(application) -> None:
        # Register commands scoped to private chats only; clear any stale group-chat scope.
        try:
            cmds = [BotCommand(n, d) for n, d in _MENU]
            await application.bot.set_my_commands(cmds, scope=BotCommandScopeAllPrivateChats())
            await application.bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())
            log.info("Registered %d slash commands with Telegram (private-chat scope).", len(_MENU))
        except Exception as exc:  # noqa: BLE001
            log.warning("set_my_commands failed: %s", exc)

        # Integrity check: warn if handlers and menu have drifted.
        menu_cmds = {cmd for cmd, _ in _MENU}
        registered_cmds: set[str] = set()
        for handler_list in application.handlers.values():
            for h in handler_list:
                if isinstance(h, CommandHandler):
                    registered_cmds.update(h.commands)
        registered_cmds.discard("start")
        missing = registered_cmds - menu_cmds
        orphaned = menu_cmds - registered_cmds
        if missing or orphaned:
            log.warning("[menu-check] Drift — handlers not in menu: %s | menu without handlers: %s",
                        sorted(missing), sorted(orphaned))
        else:
            log.info("[menu-check] Menu integrity OK — %d commands in sync.", len(_MENU))

    app = Application.builder().token(config.get("TELEGRAM_BOT_TOKEN")).post_init(_post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("context", cmd_context))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("build", cmd_build))
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(CommandHandler("note", cmd_note))
    app.add_handler(CommandHandler("missions", cmd_missions))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("status", cmd_status))
    # Advisory Runtime (MSN-0092)
    app.add_handler(CommandHandler("advisor", cmd_advisor))
    app.add_handler(CommandHandler("challenge", cmd_challenge))
    app.add_handler(CommandHandler("lessons", cmd_lessons))
    app.add_handler(CommandHandler("evidence", cmd_evidence))
    app.add_handler(CommandHandler("advisory_outcome", cmd_advisory_outcome))
    app.add_handler(CommandHandler("advisor_metrics", cmd_advisor_metrics))
    app.add_handler(CommandHandler("advisor_scan", cmd_advisor_scan))
    app.add_handler(CommandHandler("timeline", cmd_timeline))
    app.add_handler(CommandHandler("intel", cmd_intel))
    app.add_handler(CommandHandler("awareness", cmd_awareness))
    app.add_handler(CommandHandler("products", cmd_products))
    # Directed Engineering Operator
    app.add_handler(CommandHandler("eng_missions", cmd_eng_missions))
    app.add_handler(CommandHandler("eng_pickup", cmd_eng_pickup))
    app.add_handler(CommandHandler("eng_plan", cmd_eng_plan))
    app.add_handler(CommandHandler("eng_patch", cmd_eng_patch))
    app.add_handler(CommandHandler("eng_review", cmd_eng_review))
    app.add_handler(CommandHandler("eng_status", cmd_eng_status))
    app.add_handler(CommandHandler("eng_handoff", cmd_eng_handoff))
    app.add_handler(CommandHandler("eng_log", cmd_eng_log))
    app.add_handler(CallbackQueryHandler(on_eng_callback, pattern=r"^eng_(approve|cancel)$"))
    app.add_handler(CallbackQueryHandler(on_approve_callback, pattern=r"^approve_last$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    log.info("Chief Engineer agent polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
