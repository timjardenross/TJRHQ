-- 0207_revs_crisis_layer2.sql
--
-- Widens revs_crisis_events.trigger_type (migration 0147) to allow
-- 'layer2', for the new Layer-2 LLM-based crisis confirmation pass
-- (telegram-bots/revs/crisis_layer2.py) — distinct from 'language'
-- (Layer-1 regex hit, safety.py) and 'nontext' (check-in-pattern hit).
--
-- README.md's "Known gaps" / blocker #2 named this Layer 2 pass as a
-- recommended-but-unbuilt next step: safety.py's Layer-1 regex list
-- deliberately excludes bare method/acquisition nouns ("pills", "rope",
-- "bought") as too generic to match without context — a major
-- false-positive source on their own. Layer 2 runs an LLM disambiguation
-- pass only on messages containing one of those ambiguous words, to catch
-- the genuine-risk-in-context cases Layer 1 was deliberately built to
-- miss. Tagging events with 'layer2' (rather than reusing 'language')
-- keeps that distinction visible in escalation messages and in any future
-- adversarial review of the classifier's real trigger mix.

alter table public.revs_crisis_events drop constraint if exists revs_crisis_events_trigger_type_check;

alter table public.revs_crisis_events
  add constraint revs_crisis_events_trigger_type_check
  check (trigger_type in ('language', 'nontext', 'layer2'));
