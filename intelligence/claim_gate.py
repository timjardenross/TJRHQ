"""Deterministic claim gate for generated brief narratives (WP3, flag ``BRIEF_CLAIM_GATE_V1``: off | shadow | enforce).

The narrative comes from an LLM that is shown untrusted source text. This gate does not trust it: every material claim in the
narrative has to be traceable to the evidence it was written from, using lexical and structural checks only (no network, no
LLM, no clock). It is deliberately conservative: when it cannot show that a claim is supported it says so, and in enforce mode
the caller publishes a deterministic evidence-only fallback instead of the rejected narrative.

What it checks, per sentence-level claim: lexical support in the evidence, entities, figures and dates that exist in the
evidence and belong with the claim, citation and attribution targets, causal assertions, certainty wording against the
evidence's own hedging, and instruction-like or markup content. What it cannot do is understand meaning: a claim can reuse
supported words and still say something the evidence does not. The measured corpus (tests/fixtures/claim_gate) shows what is
and is not caught; do not read a pass as proof of truth.

``validate_narrative`` is a pure function. When ``mode == "enforce"`` and the result has ``passed == False`` callers MUST NOT
publish the rejected narrative.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import logging
import os
import re
import secrets
import unicodedata
from dataclasses import dataclass, field

from intelligence.weekly_evidence import (
    AGGREGATOR,
    PRIMARY,
    has_causal_language,
    publisher_family,
    source_kind,
)

log = logging.getLogger(__name__)

FLAG_NAME = "BRIEF_CLAIM_GATE_V1"
MODES = ("off", "shadow", "enforce")

STRING_FIELDS = ("executive_snapshot", "bottom_line")
LIST_FIELDS = ("emerging_themes", "forward_watch", "cps230_implications", "known_unknowns")
ALLOWED_KEYS = frozenset(STRING_FIELDS + LIST_FIELDS + ("evidence_refs",))
_STRICT_FIELDS = frozenset(STRING_FIELDS)               # factual assertions: strict lexical support
_NO_SUPPORT_FIELDS = frozenset({"known_unknowns", "so_what"})   # uncertainty / advice: no lexical-support requirement
_ADVICE_FIELDS = frozenset({"so_what"})                  # per-event recommendations: structural, predicate and causal checks only

MAX_STR_LEN = 2000
MAX_LIST_ITEMS = 12
MAX_ITEM_LEN = 600
MAX_CLAIMS = 60
STRICT_MAX_UNSUPPORTED = 0.25
RELAXED_MAX_UNSUPPORTED = 0.50

FAILURE_KINDS = ("unsupported_fact", "unsupported_causal", "fabricated_citation", "misattribution", "invented_entity",
                 "invented_date", "invented_figure", "uncertainty_misrepresented", "hostile_content")


@dataclass
class ClaimFailure:
    kind: str
    claim: str
    detail: str
    field: str = ""        # narrative field the claim sits in ("" for whole-narrative failures)
    item: int = -1         # list index within the field (-1: a string field or a whole-field failure)


@dataclass
class ClaimGateResult:
    passed: bool
    mode: str
    claims_total: int
    claims_supported: int
    failures: list[ClaimFailure] = field(default_factory=list)
    fabricated_citations: int = 0
    unsupported_causal: int = 0
    reasons: list[str] = field(default_factory=list)


def gate_mode(value: str | None = None) -> str:
    """Flag value -> off|shadow|enforce. Unset/empty is off. An UNRECOGNISED value fails to OFF (never to shadow, which would publish
    ungated text while looking enabled) and is logged loudly; callers that must not run ungated treat ``off`` as their own decision."""
    raw = os.environ.get(FLAG_NAME, "") if value is None else value
    v = (raw or "").strip().lower()
    if v in ("", "off", "0", "false", "no"):
        return "off"
    if v in MODES:
        return v
    log.warning("%s has unrecognised value %r; treating as OFF (valid values: off, shadow, enforce)", FLAG_NAME, raw)
    return "off"


# ── Text hygiene (shared by prompt hardening and the gate) ────────────────────

_CONFUSABLES = str.maketrans({"а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i", "ѕ": "s",
                              "ј": "j", "ԁ": "d", "һ": "h", "ո": "n", "ѵ": "v",
                              "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C",
                              "Т": "T", "Х": "X", "І": "I", "Ѕ": "S", "Ј": "J", "Ο": "O", "Α": "A", "Β": "B", "Ε": "E",
                              "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ρ": "P", "Τ": "T", "Χ": "X",
                              "ο": "o", "ν": "v", "ι": "i"})
# NFKC would turn superscripts and vulgar fractions into plain digits ("10²" -> "102"); keep their meaning first.
_MATH_SAFE = str.maketrans({"²": "^2", "³": "^3", "¹": "^1", "½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3"})
_URL = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
# Markup removal is a tokenizer over WELL-FORMED tags only (known element names, bare or with name=value attributes, comments,
# processing instructions, and chat-role pseudo tags). A bare '<' or '>' used as a comparison ("<2 mg", "x<3 and y>5") is never a tag.
_TAG_NAME = (r"(?:a|abbr|b|blockquote|body|br|button|code|dd|div|dl|dt|em|embed|form|h[1-6]|head|hr|html|i|iframe|img|input|li|link|"
             r"meta|object|ol|p|pre|script|span|strong|style|sub|sup|svg|table|tbody|td|th|thead|tr|u|ul|video|audio|"
             r"system|assistant|user|human|instruction|instructions|prompt|tool|function|developer|inst|sys|im_start|im_end)")
_TAG_ATTR = r"""(?:\s+[A-Za-z_:][-\w:.]*\s*=\s*(?:"[^"<>]{0,300}"|'[^'<>]{0,300}'|[^\s<>"']{1,300}))*"""
_TAG = re.compile(r"</?" + _TAG_NAME + _TAG_ATTR + r"\s*/?>|<!--.{0,600}?-->|<\?[^<>]{0,300}\?>|<!\[CDATA\[.{0,600}?\]\]>",
                  re.IGNORECASE | re.DOTALL)
_ANGLE_RUN = re.compile(r"(?:<|«|‹|⟨|《){2,}|(?:>|»|›|⟩|》){2,}")


def strip_tags(s: str) -> str:
    """Remove well-formed tags to a fixed point (so a tag cannot be re-formed from the pieces left behind)."""
    for _ in range(6):
        t = _TAG.sub(" ", s)
        if t == s:
            return t
        s = t
    return s


_NUMLIKE = re.compile(r"(?<![A-Za-z0-9])[\dOo][\dOo,.]*[\dOo](?![A-Za-z0-9])")


class _DigitFold:
    """Inside a number-shaped token that contains at least one real digit, look-alike letters O/o/l/I read as 0/0/1/1."""

    @staticmethod
    def sub(repl, s):
        def f(m):
            t = m.group(0)
            return t.translate(str.maketrans("Oo", "00")) if re.search(r"\d", t) else t
        return _NUMLIKE.sub(f, s)


_DIGIT_O = _DigitFold
_DIGIT_L = re.compile(r"(?<=\d)[lI](?=\d)")


def clean_text(text: object, *, fold: bool = True) -> str:
    """NFKC (math-safe), drop format/control characters (zero-width, bidi, etc.) and line/paragraph separators, collapse whitespace.
    With ``fold`` (the default, used for MATCHING) look-alike letters are folded to Latin and look-alike digits between digits
    become digits. Prompt text uses ``fold=False`` so genuine non-Latin text is not garbled."""
    s = unicodedata.normalize("NFKC", ("" if text is None else str(text)).translate(_MATH_SAFE))
    s = "".join(ch if (ch in "\n\t" or unicodedata.category(ch) not in ("Cf", "Cc", "Cs", "Co", "Zl", "Zp")) else (" " if unicodedata.category(ch) in ("Zl", "Zp") else "") for ch in s)
    if fold:
        s = s.translate(_CONFUSABLES)
        s = _DIGIT_L.sub("1", _DIGIT_O.sub("0", s))
    return re.sub(r"[ \t\u00a0]+", " ", s).strip()


_CTRL_CATS = ("Cc", "Cf", "Cs", "Co", "Zl", "Zp")


def has_control_chars(text: object) -> bool:
    """True when the text holds a control, format (zero-width, bidi, Unicode tag block), private-use, surrogate or line/paragraph
    separator character, other than newline, tab and carriage return. A NUL is among them (it would fail a text/jsonb insert)."""
    if not isinstance(text, str):
        return False
    return any(ch not in "\n\t\r" and unicodedata.category(ch) in _CTRL_CATS for ch in text)


def strip_control_chars(text: str) -> str:
    """Remove the characters ``has_control_chars`` reports (line/paragraph separators become a space)."""
    return "".join((" " if unicodedata.category(ch) in ("Zl", "Zp") else "") if (ch not in "\n\t\r" and unicodedata.category(ch) in _CTRL_CATS) else ch
                   for ch in text)


def sanitize_untrusted(text: object, max_len: int = 600) -> str:
    """Prepare source text for inclusion in a prompt: clean, remove markup and links, neutralise delimiters, truncate.
    Mathematical operators, doses, units and emergency-alert wording are preserved (comparison signs are not markup)."""
    s = clean_text(text, fold=False)
    s = strip_tags(s)
    s = _URL.sub("[link removed]", s)
    s = s.replace("```", "'''")
    # Any run of two or more angle-bracket characters (ASCII or common look-alikes) collapses to one, so the result can
    # never contain the three-character EVIDENCE delimiters however many characters are repeated or interleaved.
    s = _ANGLE_RUN.sub(lambda m: m.group(0)[0], s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


# ── Evidence boundaries: per-prompt random token + JSON-escaped records ────────────────────────────────────────
# Escaping delimiters is not relied on. Each evidence item is ONE line: "<token>|<json object>". The token is random per prompt,
# so source text cannot contain it or forge a closing marker; JSON escaping means a quote, backslash or line break inside a
# value cannot end the record. Text that nevertheless contains the token is withheld.

def new_boundary_token() -> str:
    return secrets.token_hex(8)


def render_evidence_block(items: list[dict], token: str) -> str:
    """``items``: dicts of already-sanitised short strings. Returns one line per item, then an end line."""
    lines: list[str] = []
    for it in items:
        rec = {k: ("" if v is None else v) for k, v in it.items()}
        blob = json.dumps(rec, ensure_ascii=False)
        if token in blob:
            rec = {"id": rec.get("id", ""), "withheld": "boundary collision"}
            blob = json.dumps(rec, ensure_ascii=False)
        lines.append(f"{token}|{blob}")
    lines.append(f"{token}|END")
    return "\n".join(lines)


# ── Hostile content ───────────────────────────────────────────────────────────

_HOSTILE = [re.compile(p, re.IGNORECASE) for p in (
    r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+|your\s+)*(?:previous|prior|above|earlier|preceding|system)\b",
    r"\bnew\s+instructions?\b",
    r"\bsystem\s*(?:prompt|message)\b",
    r"\bdeveloper\s+message\b",
    r"(?:^|[\s\[(])(?:system|assistant|developer)\s*:",
    r"\byou\s+are\s+now\b",
    r"\bas\s+an\s+ai\b",
    r"\blanguage\s+model\b",
    r"\bjailbreak",
    r"\breveal\s+(?:your|the)\s+(?:prompt|instructions?|rules)\b",
    r"\b(?:wire|transfer|send)\s+(?:the\s+)?(?:funds|money|payment)\b",
    r"\bclick\s+(?:here|the\s+link)\b",
    r"\bvisit\s+(?:https?://|www\.)",
    r"<\s*(?:script|iframe|object|embed|img|svg|style)\b",
    r"javascript\s*:",
    r"\bon(?:error|load|click)\s*=",
    r"\[[^\]]{0,120}\]\(\s*(?:https?:)?//",
    r"\bdo\s+not\s+(?:tell|mention|reveal|disclose)\b",
    r"\boutput\s+(?:only\s+)?['\"]?all\s+clear\b",
    r"\b(?:respond|reply)\s+with\b",
    # Paraphrased directives aimed at whoever summarises the text (not ordinary alert wording such as "please evacuate").
    r"\b(?:kindly|please|just|simply)\s+(?:present|describe|portray|characteri[sz]e|summari[sz]e|conclude|state|say|write|word|frame|label|mark|rate|classify|tell\s+(?:the\s+)?(?:captain|reader|user|reviewer))\b",
    r"\b(?:present|describe|portray|characteri[sz]e|frame|label|classify|rate|mark|report|summari[sz]e)\s+(?:this|it|the\s+(?:incident|event|outage|story|situation))\s+as\b",
    r"\b(?:you|the\s+(?:summary|brief|report|narrative|assistant|author|writer|reader|reviewer))\s+(?:must|should|shall|need\s+to|have\s+to)\s+(?:say|state|conclude|write|present|describe|rate|mark|call|treat|tell|inform|assure|reassure|avoid|omit|exclude|not\s+(?:mention|flag|escalate|raise|include))\b",
    r"\b(?:do\s+not|don'?t|never)\s+(?:flag|escalate|raise|alert|highlight|include|list|rate)\b",
    r"\b(?:downplay|play\s+down|understate|suppress\s+(?:this|the|any))\b",
    r"\b(?:make\s+sure|ensure)\s+(?:to\s+|that\s+)?(?:say|state|mention|conclude|report|write|the\s+(?:brief|summary|reader))\b",
    r"\b(?:assistant|chatbot|llm|summari[sz]er|ai\s+(?:model|system|agent))\b.{0,30}\b(?:must|should|will|shall|is\s+to|are\s+to)\b",
    r"\bwhen\s+(?:summari[sz]ing|writing|generating|producing)\b",
    # Meta-address (round 3): source text that speaks to whoever reads, writes or summarises it, or to the Captain, about how to present
    # the matter. Ordinary alert wording ("residents should leave", "customers should check") never addresses the author or reader.
    r"\breaders?\s+of\s+(?:this|the)\s+(?:digest|brief|summary|report|page|article|post|note|feed|bulletin)\b[^.!?\n]{0,60}\b(?:should|must|ought|need\s+to|have\s+to)\b",
    r"\bwhoever\s+(?:reads?|compil\w+|summari[sz]\w+|writ\w+|produc\w+|prepar\w+|draft\w+|review\w*)\b[^.!?\n]{0,60}\b(?:should|must|ought|needs?\s+to|has\s+to|is\s+to)\b",
    r"\b(?:any|every|each)\s+(?:summary|summaries|brief|digest|report|write-?up|narrative|analysis|assessment)\b[^.!?\n]{0,60}\b(?:should|must|ought|need\s+to|has\s+to|is\s+to|would\s+do\s+well)\b",
    r"\b(?:in|for)\s+(?:your|any)\s+(?:write-?up|summary|brief|digest|report)\b",
    r"\bfor\s+the\s+purposes?\s+of\s+(?:the|this|any)\s+(?:executive\s+)?(?:summary|brief|digest|report)\b",
    r"\bcaptain\b[^.!?\n]{0,30}\b(?:does\s+not\s+need|doesn'?t\s+need|need\s+not|should\s+not|must\s+not|can\s+ignore|can\s+skip)\b",
    r"\b(?:it\s+(?:would\s+be|is)|it'?s)\s+(?:appropriate|advisable|best|wise|sensible|preferable|correct)\s+to\s+(?:describe|say|state|call|treat|rate|label|present|characteri[sz]e|conclude|classify|mark|frame|report|portray|mention|rank)\b",
    r"\b(?:treat|regard|consider|deem|view)\s+(?:the\s+|this\s+|these\s+|all\s+)?(?:[\w'’-]+\s+){0,3}(?:matter|issue|incident|event|outage|story|alert|situation|items?|incidents)\s+as\s+(?:routine|minor|low|trivial|benign|non-?urgent|harmless|resolved|safe|fine|closed)\b",
    r"\b(?:notice|note|message|attention)\s+(?:to|for)\s+(?:the\s+)?(?:ai|llm|assistant|model|summari[sz]er|bot|reviewer|analyst)\b",
    r"\bmake\s+a\s+point\s+of\s+(?:saying|stating|mentioning|noting|writing)\b",
    r"\b(?:a|any)\s+(?:good|careful|sensible|competent|diligent)\s+(?:analyst|summari[sz]er|author|writer|assistant)\s+(?:would|should|will)\b",
    r"\b(?:summari[sz]ers?|reporters|analysts|authors|writers|compilers|assistants?)\b[^.!?\n]{0,30}\b(?:are|is)\s+(?:expected|required|asked|instructed|supposed)\s+to\b",
    r"\bought\s+to\s+conclude\b",
    r"(?:^|[.!?]\s+)(?:please\s+)?(?:treat|describe|present|regard|conclude|summari[sz]e|classify|characteri[sz]e|portray|frame|label)\s+[^.!?\n]{0,60}?\bas\b",
)]


def hostile_hits(text: object) -> list[str]:
    s = clean_text(text)
    return [p.pattern[:40] for p in _HOSTILE if p.search(s)]


# Phrases that also occur in genuine public alerts ("Respond with caution", "click here for the map", "visit www.example.gov") are not
# treated as injection in SOURCE text on their own; unambiguous echo phrasing ("reply with 'all clear'") still is. The NARRATIVE may
# not contain any of them (it is checked with the full list), so an alert's wording is summarised, never relayed as a command.
WEAK_MARKERS = (r"\bclick\s+(?:here|the\s+link)\b", r"\bvisit\s+(?:https?://|www\.)", r"\b(?:respond|reply)\s+with\b")
STRONG_HOSTILE = [p for p in _HOSTILE if p.pattern not in WEAK_MARKERS]
ECHO_REPLY = re.compile(r"\b(?:respond|reply)\s+with\s+(?:only\s+)?['\"]?(?:all\s+clear|nothing|ok|okay|yes|no|safe)\b", re.IGNORECASE)


def source_instruction_like(*texts: object) -> bool:
    """True only for genuinely instruction-like SOURCE text (emergency-alert phrasing alone does not count)."""
    for t in texts:
        s = clean_text(t)
        if ECHO_REPLY.search(s) or any(p.search(s) for p in STRONG_HOSTILE):
            return True
    return False


# Phishing-shaped SOURCE text (a number to call or details to hand over, tied to an account or payment). Genuine alert wording that names a
# hotline ("call 000", "VicEmergency hotline 1800 226 226") has no account/payment/verification element and is not matched.
_PHONE = re.compile(r"(?<!\d)(?:\+?61|0)[2-478](?:[\s-]?\d){8}(?!\d)|(?<!\d)1[38]00(?:[\s-]?\d){6}(?!\d)|(?<!\d)\+?\d{1,3}[\s-]\d{2,4}[\s-]\d{3,4}[\s-]\d{3,4}(?!\d)")
_SCAM_ACTION = re.compile(r"\b(?:call|ring|phone|contact|text|sms|message|whatsapp|log\s?in|sign\s?in|click|enter|provide|send|confirm|verify|update)\b", re.IGNORECASE)
_SCAM_TARGET = re.compile(r"\b(?:bank|account|password|passcode|pin|card|payment|refund|prize|winner|gift\s?card|bitcoin|crypto|tax\s+refund|identity|verify\s+your|confirm\s+your|login|credentials|details)\b", re.IGNORECASE)


def scam_like(*texts: object) -> bool:
    """True for source text that looks like a phishing or payment lure (phone number or credentials request tied to an account or payment)."""
    for t in texts:
        s = clean_text(t)
        if _SCAM_ACTION.search(s) and _SCAM_TARGET.search(s) and (_PHONE.search(s) or re.search(r"\b(?:verify|confirm|update|enter|provide)\s+(?:your|the)\b", s, re.IGNORECASE)):
            return True
    return False


# ── Lexical machinery ─────────────────────────────────────────────────────────

_SKIP = frozenset(["the", "and", "for", "with", "that", "this", "from", "have", "has", "had", "were", "was", "are", "been", "being", "will", "would", "could", "should", "might", "shall", "must", "may", "can", "not", "but", "than", "then", "them", "they", "their", "there", "these", "those", "which", "while", "where", "when", "what", "whether", "who", "whom", "whose", "into", "onto", "over", "under", "about", "around", "across", "also", "still", "only", "very", "some", "many", "most", "more", "less", "other", "such", "each", "every", "both", "either", "neither", "between", "during", "within", "through", "against", "among", "after", "before", "since", "until", "upon", "per", "via", "its", "our", "your", "his", "her", "him", "she", "you", "any", "all", "one", "two", "said", "says", "say", "stated", "state", "states", "reported", "report", "reports", "reporting", "announced", "announce", "announces", "noted", "note", "told", "tell", "confirmed", "confirm", "confirms", "likely", "possible", "possibly", "potentially", "significant", "significantly", "important", "key", "risk", "risks", "resilience", "operational", "organisation", "organisations", "organization", "organizations", "consider", "considers", "monitor", "monitoring", "watch", "implication", "implications", "relevant", "relates", "relate", "following", "remain", "remains", "remaining", "ensure", "review", "reviews", "continue", "continues", "currently", "include", "includes", "including", "several", "same", "new", "now", "today", "week", "month", "year", "incident", "incidents", "problem", "problems", "issue", "issues", "service", "services", "event", "events", "situation", "development", "developments", "rated", "rating", "amber", "green", "posture", "active", "period", "both", "highlight", "highlights", "underscore", "underscores", "reinforce", "reinforces", "demonstrate", "demonstrates", "illustrate", "illustrates", "show", "shows", "suggest", "suggests", "indicate", "indicates", "reminder", "lesson", "importance", "need", "needs", "preparedness", "continuity", "planning", "vigilance", "attention", "scrutiny", "unconfirmed", "unverified", "reportedly", "alleged", "allegedly", "company", "whilst", "however", "therefore", "thus", "because", "caused", "cause", "causes", "due", "owing", "led", "leads", "leading", "result", "results", "resulted", "resulting", "trigger", "triggered", "triggers", "attributed", "stemmed", "stems", "blamed", "blame", "driven", "cited", "citing", "cites", "reason", "reasons", "why", "known", "unclear", "unknown", "uncertain", "undetermined", "explanation", "explained", "watch"])

_COMMON_INITIAL = frozenset(["further", "any", "repeat", "repeated", "additional", "official", "confirmation", "publication", "notice",
    "guidance", "evidence", "restoration", "disruption", "dependence", "exposure", "costs", "cost", "delays", "delay", "firms", "firm", "pressure", "institutions", "entities", "boards", "board",
    "compliance", "timeframes", "obligations", "reliance", "smaller", "faster", "shorter", "earlier", "later", "manual", "without",
    "the", "a", "an", "this", "that", "these", "those", "it", "its", "there", "here", "some", "many", "several", "most", "all", "any", "each", "every", "no", "not", "new", "following", "after", "before", "during", "while", "when", "where", "if", "as", "at", "in", "on", "of", "to", "for", "with", "from", "by", "and", "but", "or", "so", "yet", "both", "either", "neither", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "other", "another", "more", "less", "few", "multiple", "early", "late", "recent", "latest", "current", "currently", "also", "however", "meanwhile", "overall", "although", "though", "since", "until", "once", "only", "just", "still", "even", "such", "regulators", "authorities", "customers", "users", "services", "engineers", "crews", "officials", "analysts", "reports", "sources", "media", "agencies", "companies", "organisations", "organizations", "people", "residents", "households", "businesses", "banks", "providers", "operators", "investigators", "public", "health", "consider", "review", "check", "assess", "confirm", "ensure", "verify", "prepare", "track", "expect", "treat", "note", "watch", "keep", "maintain", "update", "flooding", "flood", "storm", "fire", "outage", "outages", "cyber", "security", "risk", "risks", "threat", "threats", "alert", "alerts", "warning", "warnings", "emergency", "both", "separately", "additionally", "furthermore", "finally", "first", "second", "third", "next", "last", "today", "yesterday", "tomorrow", "cloud", "internet", "network", "networks", "payments", "payment", "banking", "mobile", "software", "hardware", "data", "power", "energy", "transport", "telecom", "telecommunications", "digital", "hospital", "hospitals", "airline", "airlines", "aviation", "financial", "finance", "supply", "grid", "broadband", "wireless", "satellite", "storage", "hosting", "vendor", "vendors", "supplier", "suppliers", "third", "regulatory", "sector", "sectors", "systemic", "critical", "infrastructure", "risk", "medical", "safety"])

_ENTITY_ALLOW = frozenset(["australia", "australian", "australians", "captain", "tjr", "cps", "ai", "red", "amber", "green", "unknown", "emergency", "warning", "watch", "act", "advice", "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec"])

_SYN = {"disrupt": "outage", "disruption": "outage", "interrupt": "outage", "interruption": "outage", "fault": "outage",
        "failure": "outage", "fail": "outage", "restor": "restor", "recover": "restor", "resum": "restor",
        "user": "custom", "subscrib": "custom", "impact": "affect", "hit": "affect",
        "offline": "outage", "down": "outage", "knock": "outage", "began": "start", "begin": "start", "commenc": "start",
        "fix": "restor", "return": "restor", "warn": "advis", "advise": "advis", "urge": "advis", "recommend": "advis",
        "slowdown": "slow", "slowing": "slow", "slowed": "slow", "slowness": "slow", "intermittently": "intermittent", "unavailable": "outage"}

# Generic analytical vocabulary: words that carry no incident-specific fact. Ignored for the support ratio of the analytical LIST fields only
# (themes, forward watch, CPS 230 implications), never for the executive snapshot / bottom line.
_ANALYSIS_VOCAB = frozenset(["obligation", "obligations", "dependency", "dependencies", "resilience", "operational", "regulatory", "compliance", "critical", "operations", "third-party", "tolerance", "notification", "board", "governance", "concentration", "continuity", "contingency", "telecommunications", "telecommunication", "touches", "touch", "relevance", "relevant", "exposure", "supplier", "suppliers", "vendor", "vendors", "communications", "customers"])

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_WEEKDAY_RE = re.compile(r"\b(" + "|".join(_WEEKDAYS) + r")\b", re.IGNORECASE)
# Regulatory standard references: the number is part of the name, not a reported figure.
_STD_REF = re.compile(r"\b(?:CPS|CPG)\s*(?:230|231|232|234)\b", re.IGNORECASE)
_VAGUE_NUM = re.compile(r"\b(?:a|one)\s+(million|billion|thousand|hundred|dozen)\b", re.IGNORECASE)
_LARGE_Q = re.compile(r"\b(millions|billions|thousands|hundreds|tens\s+of\s+thousands|hundreds\s+of\s+thousands)\s+of\b", re.IGNORECASE)
_LARGE_MIN = {"millions": 2e6, "billions": 2e9, "thousands": 2e3, "hundreds": 200, "tens of thousands": 2e4, "hundreds of thousands": 2e5}


def _stem_set(words) -> set[str]:
    return {_stem(w) for w in words} | set(words)


def _stem(w: str) -> str:
    w = w.lower().replace("’", "'")
    w = w.removesuffix("'s")
    if len(w) > 5:
        for suf in ("ations", "ation", "ings", "ing", "ed", "es", "s", "ly"):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                break
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return _SYN.get(w, w)


_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'’-]*")
_ID = re.compile(r"\b[A-Z]{2,6}-\d{2,4}-\d{2,7}\b")
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DATE_DM = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MON + r"\b", re.IGNORECASE)
_DATE_MD = re.compile(r"\b" + _MON + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.IGNORECASE)
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_NUM = re.compile(r"(?<![\w.])(?:A\$|US\$|\$)?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(%|percent|per cent|million|billion|thousand|bn|m|k)?(?![\w])",
                  re.IGNORECASE)
_NUMWORD = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
            "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
            "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
            "hundred": 100, "dozen": 12}
_NUMWORD_RE = re.compile(r"\b(" + "|".join(_NUMWORD) + r")(?:\s+(hundred|thousand|million|billion))?\b", re.IGNORECASE)
_MULT = {"million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "thousand": 1e3, "k": 1e3}
_META_NOUN = re.compile(r"^\s*(?:sources|publishers|domains|items|events|themes|signals|reports|incidents|stories|articles)\b", re.IGNORECASE)


def dates_in(text: str) -> tuple[set[tuple[int, int]], str]:
    """(month, day) pairs mentioned, and the text with date spans blanked so their digits are not read as figures."""
    out: set[tuple[int, int]] = set()
    t = text
    for m in _DATE_ISO.finditer(t):
        out.add((int(m.group(2)), int(m.group(3))))
    t = _DATE_ISO.sub(" ", t)
    for m in _DATE_DM.finditer(t):
        out.add((_MONTHS[m.group(2)[:3].lower()], int(m.group(1))))
    t = _DATE_DM.sub(" ", t)
    for m in _DATE_MD.finditer(t):
        out.add((_MONTHS[m.group(1)[:3].lower()], int(m.group(2))))
    t = _DATE_MD.sub(" ", t)
    return out, t


_TIME_AMPM = re.compile(r"(?<![\d:.])(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)(?![A-Za-z])", re.IGNORECASE)
_TIME_24 = re.compile(r"(?<![\d:.,$])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])(?:\s*(?:hrs|hours|AEDT|AEST|UTC|GMT|AWST|ACST|ACDT))?", re.IGNORECASE)
_TIME_WORD = re.compile(r"\b(noon|midday|midnight)\b", re.IGNORECASE)
_DAYPARTS = {"morning": "morning", "afternoon": "afternoon", "evening": "evening", "overnight": "night", "night": "night", "dawn": "morning"}
_DAYPART_RE = re.compile(r"\b(morning|afternoon|evening|overnight|night|dawn)\b", re.IGNORECASE)


def times_in(text: str) -> tuple[set[int], str]:
    """Clock times mentioned (minutes after midnight) and the text with the time spans blanked. ``9am``, ``2:30pm``, ``14:45``, noon, midnight."""
    out: set[int] = set()
    t = text

    def _am(m):
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower().replace(".", "")
        if 1 <= h <= 12:
            out.add(((h % 12) + (12 if ap == "pm" else 0)) * 60 + mi)
        return " "
    t = _TIME_AMPM.sub(_am, t)

    def _h24(m):
        out.add(int(m.group(1)) * 60 + int(m.group(2)))
        return " "
    t = _TIME_24.sub(_h24, t)
    for m in _TIME_WORD.finditer(t):
        out.add(0 if m.group(1).lower() == "midnight" else 720)
    return out, _TIME_WORD.sub(" ", t)


def dayparts_in(text: str) -> set[str]:
    return {_DAYPARTS[m.group(1).lower()] for m in _DAYPART_RE.finditer(text)}


def daypart_of_minute(t: int) -> str:
    return "morning" if t < 720 else "afternoon" if t < 1020 else "evening" if t < 1260 else "night"


def figures_in(text: str) -> tuple[set[float], set[str]]:
    """(numeric values, identifiers such as CVE ids). Values 0-2 and plausible years are ignored; word numbers three+ count."""
    ids = {m.group(0).upper() for m in _ID.finditer(text)}
    t = _ID.sub(" ", text)
    _, t = dates_in(t)
    _, t = times_in(t)
    vals: set[float] = set()
    for m in _NUM.finditer(t):
        raw, suf = m.group(1), (m.group(2) or "").lower()
        try:
            v = float(raw.replace(",", ""))
        except ValueError:
            continue
        if suf in _MULT:
            v *= _MULT[suf]
        if suf not in ("%", "percent", "per cent") and v <= 2 and not suf:
            continue
        if not suf and 1990 <= v <= 2100 and "," not in raw and "." not in raw:
            continue
        vals.add(round(v, 4))
    for m in _NUMWORD_RE.finditer(t):
        if _META_NOUN.match(t[m.end():]):
            continue
        v = float(_NUMWORD[m.group(1).lower()])
        if m.group(2):
            v *= {"hundred": 100, "thousand": 1e3, "million": 1e6, "billion": 1e9}[m.group(2).lower()]
        vals.add(round(v, 4))
    for m in _VAGUE_NUM.finditer(t):
        vals.add(float({"million": 1e6, "billion": 1e9, "thousand": 1e3, "hundred": 100, "dozen": 12}[m.group(1).lower()]))
    return vals, ids


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9$])|\n+", text.strip())
    return [p.strip() for p in parts if p and re.search(r"[A-Za-z]{2,}", p)]


def _content_stems(text: str, exclude: set[str] | None = None) -> set[str]:
    exclude = exclude or set()
    out = set()
    for w in _WORD.findall(clean_text(text)):
        lw = w.lower()
        if len(lw) < 3 or lw in _SKIP or lw in exclude:
            continue
        out.add(_stem(lw))
    return out


_CAUSAL_EXT = re.compile(r"\bcaus(?:e|es|ed|ing)\b|\bbecause\b|\bdue\s+to\b|\bowing\s+to\b|\bled\s+to\b|\bleads?\s+to\b|\bleading\s+to\b|\bresult(?:s|ed|ing)?\s+(?:in|from)\b|\bas\s+a\s+result\b|\bconsequen\w*|\btrigger(?:s|ed|ing)?\b|\bprompt(?:s|ed|ing)\b|\battribut(?:ed|able|es)\s+to\b|\bstem(?:s|med|ming)\s+from\b|\bdriven\s+by\b|\bblam(?:e|ed|es|ing)\b|\bresponsible\s+for\b|\bbehind\s+the\b|\bthanks\s+to\b|\btherefore\b|\bhence\b|\bthe\s+reason\b|\bsparked\b|\bculminat\w+|\bgave\s+rise\b", re.IGNORECASE)


def causal(text: str) -> bool:
    return bool(has_causal_language(text) or _CAUSAL_EXT.search(text or ""))


_HEDGE = re.compile(r"\b(?:unconfirmed|unverified|reportedly|alleged(?:ly)?|suggest(?:s|ed)?|claims?|claimed|rumou?rs?|speculat\w+|"
                    r"not\s+(?:yet\s+)?(?:been\s+)?confirmed|(?:has|have|had)\s+not\s+(?:yet\s+)?(?:confirmed|stated|said|responded)|"
                    r"no\s+confirmation|denied|denies|disputed?|may\s+have|might|possibly|suspected|believed|appears?|yet\s+to|"
                    r"not\s+yet|did\s+not\s+respond|unclear|unknown)\b", re.IGNORECASE)
_NEG_CONFIRM = re.compile(r"\b(?:unconfirmed|not\s+(?:yet\s+)?(?:been\s+)?confirmed|(?:has|have|had)\s+not\s+(?:yet\s+)?confirmed|"
                          r"yet\s+to\s+(?:be\s+)?confirm\w*|cannot\s+confirm|unable\s+to\s+confirm|no\s+confirmation|"
                          r"not\s+(?:yet\s+)?verified|unverified)\b", re.IGNORECASE)
_STRONG = re.compile(r"\b(?:confirm(?:ed|s)?|verified|definitiv\w+|established|proven|undisputed|beyond\s+doubt|corroborated|"
                     r"officially|authoritative|it\s+is\s+certain|is\s+certain|certainly|certain\s+that|is\s+now\s+a\s+verified|"
                     r"indisputabl\w+|conclusively)\b", re.IGNORECASE)
_MULTI_SOURCE = re.compile(r"\b(?:multiple|several|numerous|many|independent|widely\s+reported|corroborat\w+)\s*(?:independent\s+)?sources?\b|"
                           r"\bwidely\s+reported\b", re.IGNORECASE)
_NEGATION = re.compile(r"\b(?:not|no|never|none|neither|nor|without|cannot)\b|n't\b", re.IGNORECASE)
_AFFIRM = re.compile(r"\b(?:confirm(?:ed|s)?|announce[sd]?|ordered|stated|said|reported|restored|deployed|disclosed)\b", re.IGNORECASE)

_CITE_STYLE = re.compile(
    r"(?i:\b(?:according\s+to|as\s+reported\s+by|reported\s+by|reports?\s+from|citing|via|source\s*:|sources\s*:|per))\s+"
    r"(?:the\s+)?([A-Z][\w&.'’-]*(?:\s+(?:of|for|and|the)?\s*[A-Z][\w&.'’-]*){0,3})")
_SPEAKER = re.compile(
    r"\b(?:The\s+)?([A-Z][\w&'’-]*(?:\s+[A-Z][\w&'’-]*){0,3})\s+"
    r"(?:said|says|reported|reports|confirmed|announced|stated|warned|noted|told|disclosed|revealed|blamed|claimed|ordered)\b")
_INLINE_REF = re.compile(r"\[([A-Za-z]{0,4}[-\w]*\d[-\w]*)\]")


@dataclass
class _Ev:
    id: str
    text: str
    sents: list[str]
    stems: set[str]
    tstems: set[str]
    ents: set[str]            # lowercase words (title+summary+source) used for entity/attribution membership
    figs: set[float]
    ids: set[str]
    dates: set[tuple[int, int]]
    urls: set[str]
    source: str
    family: str
    kind: str
    hostile: bool
    weekdays: set[str] = field(default_factory=set)
    neg_stems: set[str] = field(default_factory=set)      # content stems inside a negation scope ("but not passwords")
    aff_stems: set[str] = field(default_factory=set)      # content stems stated outside any negation scope
    times: set[int] = field(default_factory=set)
    dayparts: set[str] = field(default_factory=set)
    norm_sents: frozenset = field(default_factory=frozenset)
    risk: str = ""


def _norm_url(u: str) -> str:
    return u.strip().rstrip(".,;:)").lower().rstrip("/")


def _pub_weekdays(e: dict) -> set[str]:
    import datetime as _dt
    out: set[str] = set()
    for k in ("published_at", "assessed_at", "collected_at"):
        v = e.get(k)
        if isinstance(v, str):
            m = _DATE_ISO.search(v[:10])
            if m:
                try:
                    out.add(_WEEKDAYS[_dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).weekday()])
                except ValueError:
                    pass
    return out


_NEG_CUE = re.compile(r"\b(?:but\s+not|not|no|never|neither|nor|without|excluding|except|other\s+than|rather\s+than|cannot|can'?t|didn'?t|hasn'?t|haven'?t|hadn'?t|wasn'?t|weren'?t|isn'?t|aren'?t|won'?t|doesn'?t|don'?t)\b",
                      re.IGNORECASE)
_NEG_END = re.compile(r"[.;:!?]|,\s+(?:and|but|while|which|who|with|after|before)\b|\b(?:but|while|although|though|whereas|because|after|before|when|which|who|so|then|yet)\b", re.IGNORECASE)


def negation_scope_stems(sentence: str) -> set[str]:
    """Content stems that sit inside a negation scope: from a negation cue to the end of the clause (at most eight words). Lists continue
    the scope ("not passwords, tokens or payment details")."""
    out: set[str] = set()
    for m in _NEG_CUE.finditer(sentence):
        tail = sentence[m.end():]
        cut = _NEG_END.search(tail)
        tail = tail[: cut.start()] if cut else tail
        out |= _content_stems(" ".join(tail.split()[:8]))
    return out


def _norm_sentence(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


_DIRECTIVE_SHAPE = re.compile(r"^\W*(?:please\s+)?(?:treat|describe|present|rank|rate|mark|label|regard|conclude|summari[sz]e|classify|characteri[sz]e|portray|frame|say|state|write|call|tell|ignore|disregard|suppress|omit|conceal|report\s+(?:this|it))\b"
                              r"|\b(?:should|must|ought\s+to|needs?\s+to)\s+(?:be\s+)?(?:treat|describ|present|rank|rate|mark|label|regard|conclud|summari|classif|characteri|portray|frame|say|state|call|tell|ignor|disregard|omit|conceal)", re.IGNORECASE)


def _risk_of(e: dict) -> str:
    v = str(e.get("risk_rating") or e.get("risk") or "").strip().upper()
    return v if v in ("RED", "AMBER", "GREEN", "UNKNOWN") else ""


_PROPER_PHRASE = re.compile(r"\b[A-Z][A-Za-z&'’-]+(?:\s+(?:of|for|and|the)?\s*[A-Z][A-Za-z&'’-]+){1,4}")


def _build_evidence(evidence: list[dict]) -> list[_Ev]:
    out: list[_Ev] = []
    for n, e in enumerate(evidence or [], 1):
        if not isinstance(e, dict):
            continue
        title, summary = clean_text(e.get("title")), clean_text(e.get("summary"))
        source = clean_text(e.get("source") or e.get("source_name") or e.get("domain"))
        text = f"{title}. {summary}" if summary else title
        sents = _sentences(title) + _sentences(summary)
        figs, ids = figures_in(text)
        ds, _ = dates_in(text)
        for k in ("published_at", "assessed_at", "collected_at"):
            v = e.get(k)
            if isinstance(v, str):
                ds |= dates_in(v[:10])[0]
        words = {w.lower() for w in _WORD.findall(f"{text} {source} {clean_text(e.get('location'))}")}
        words |= {_stem(w) for w in words}
        for m_ in _PROPER_PHRASE.finditer(f"{title}. {summary}. {source}"):     # initialisms: AFR for Australian Financial Review
            ws_ = [w for w in re.findall(r"[A-Za-z]+", m_.group(0)) if w.lower() not in ("of", "for", "and", "the")]
            if len(ws_) >= 2:
                words.add("".join(w[0] for w in ws_).lower())
        urls = {_norm_url(str(u)) for u in (e.get("canonical_url"), e.get("url")) if u}
        neg, aff = set(), set()
        for sent in sents:
            ns = negation_scope_stems(sent)
            neg |= ns
            aff |= _content_stems(sent) - ns
        tms, _ = times_in(text)
        out.append(_Ev(id=str(e.get("id") or f"E{n}"), text=text, sents=sents, stems=_content_stems(text), tstems=_content_stems(title), ents=words, figs=figs,
                       ids=ids, dates=ds, urls=urls, source=source, family=publisher_family(source, title),
                       kind=source_kind(source), hostile=source_instruction_like(f"{title} {summary}"),
                       weekdays=_pub_weekdays(e), neg_stems=neg, aff_stems=aff, times=tms, dayparts=dayparts_in(text),
                       norm_sents=frozenset(_norm_sentence(x) for x in sents if len(_norm_sentence(x).split()) >= 3), risk=_risk_of(e)))
    return out


_COMMON_SUFFIX = re.compile(r"(?:ing|ed|ly|tion|sion|ment|ness|ity|ous|ive|ful|less|able|ible|ize|ise)$", re.IGNORECASE)


def _entities(sentence: str) -> tuple[list[str], list[str]]:
    """(mid-sentence capitalised words and acronyms, sentence-initial uncommon capitalised words)."""
    mid, initial = [], []
    words = list(_WORD.finditer(sentence))
    for i, m in enumerate(words):
        w = re.sub(r"['’]s$", "", m.group(0))
        if not w or not w[0].isupper():
            continue
        if w.lower() in _ENTITY_ALLOW or (len(w) == 1):
            continue
        prefix = sentence[: m.start()].rstrip("([\"' ")
        at_start = i == 0 or prefix == "" or prefix[-1:] in ".!?:;"
        if w.isupper() and len(w) >= 2:
            mid.append(w)
        elif at_start:
            parts = w.lower().split("-")
            if parts[0] in _COMMON_INITIAL or w.lower() in _COMMON_INITIAL:
                continue
            if w.lower() not in _COMMON_INITIAL and w.lower() not in _SKIP and not _COMMON_SUFFIX.search(w):
                initial.append(w)
        else:
            mid.append(w)
    return mid, initial


# ── Gate ──────────────────────────────────────────────────────────────────────

def _claims_of(narrative: dict) -> tuple[list[tuple[str, str, int]], list[ClaimFailure]]:
    """(field, sentence, list item index) for every sentence-level claim, plus structural problems. Control and invisible characters in any
    string are a problem on their own (they would be stored and displayed as written)."""
    claims: list[tuple[str, str, int]] = []
    problems: list[ClaimFailure] = []
    for f in STRING_FIELDS:
        v = narrative.get(f)
        if v is None or v == "":
            continue
        if not isinstance(v, str):
            problems.append(ClaimFailure("unsupported_fact", f, "field is not text", f))
            continue
        if len(v) > MAX_STR_LEN:
            problems.append(ClaimFailure("unsupported_fact", f, f"field longer than {MAX_STR_LEN} characters", f))
            continue
        if has_control_chars(v):
            problems.append(ClaimFailure("hostile_content", f, "control, invisible or direction-override characters in the text", f))
        claims += [(f, s_, -1) for s_ in _sentences(v)]
    for f in LIST_FIELDS:
        v = narrative.get(f)
        if v is None or v == []:
            continue
        if not isinstance(v, list) or len(v) > MAX_LIST_ITEMS or not all(isinstance(x, str) for x in v):
            problems.append(ClaimFailure("unsupported_fact", f, "field is not a short list of text", f))
            continue
        for i, x in enumerate(v):
            if len(x) > MAX_ITEM_LEN:
                problems.append(ClaimFailure("unsupported_fact", f, f"item longer than {MAX_ITEM_LEN} characters", f, i))
                continue
            if has_control_chars(x):
                problems.append(ClaimFailure("hostile_content", f, "control, invisible or direction-override characters in the text", f, i))
            claims += [(f, s_, i) for s_ in _sentences(x)]
    return claims, problems


def _pick_support(stems: set[str], ents_l: list[str], evs: list[_Ev], *, coordinated: bool) -> tuple[list[_Ev], set[str]]:
    """Evidence a claim may lean on. A claim that is not a coordination of several statements must be supported by ONE story
    (the best-matching item plus other reports of the same story); a coordinated claim may draw on up to three items."""
    pool = [e for e in evs if not e.hostile]
    chosen: list[_Ev] = []
    covered: set[str] = set()
    if not coordinated:
        best = _best_single(stems, evs)
        if best is None:
            return [], set()
        chosen = [best] + [e for e in pool if e is not best and e.tstems and best.tstems
                           and len(e.tstems & best.tstems) / len(e.tstems | best.tstems) >= 0.25]
        for e in chosen:
            covered |= stems & e.stems
        return chosen, covered
    for _ in range(3):
        best, gain = None, 0
        for e in pool:
            if e in chosen:
                continue
            g = len((stems & e.stems) - covered) + sum(1 for w in ents_l if w in e.ents) * 0.5
            if g > gain:
                best, gain = e, g
        if best is None:
            break
        chosen.append(best)
        covered |= stems & best.stems
        if covered >= stems:
            break
    return chosen, covered


def _best_single(stems: set[str], evs: list[_Ev]) -> _Ev | None:
    pool = [e for e in evs if not e.hostile]
    if not pool:
        return None
    return max(pool, key=lambda e: len(stems & e.stems))


def _has_word(ev: _Ev, name: str) -> bool:
    words = [w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in ("the", "of", "for", "and")]
    return bool(words) and all(w in ev.ents or _stem(w) in ev.ents for w in words)


# ── Added checks (fix-logic): predicates, per-clause polarity, cause roles, coverage statements ─────────────────────────────

_CLAUSE_SPLIT = re.compile(r"(?<!\d),|,(?!\d)|[;:]|\s[-–—]\s|\b(?:but|and|while|although|though|whereas|however|after|before|because|as|that|which|who|whom|whose|where|when|since|until|so)\b", re.IGNORECASE)
_POL_STOP = frozenset(["the", "and", "for", "with", "that", "this", "from", "have", "has", "had", "were", "was", "are", "been", "being", "will", "would", "could", "should", "its", "their", "there", "about", "over", "into", "than", "then", "also", "yet", "still", "just", "only", "said", "says", "affected", "reported", "stated", "announced", "customers"])
_CLAUSE_COARSE = re.compile(r"[;:]|\s[-–—]\s|\b(?:but|while|although|though|whereas|however)\b|[.!?]", re.IGNORECASE)


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in _CLAUSE_SPLIT.split(text) if c and re.search(r"[A-Za-z]{3,}", c)]


def _pol_tokens(text: str) -> set[str]:
    """Content tokens used to pair a claim clause with an evidence clause for the polarity check. Names (capitalised words after the first)
    carry no polarity, so two clauses that only share names are not paired."""
    out = set()
    for i, w in enumerate(_WORD.findall(clean_text(text))):
        if len(w) >= 4 and w.lower() not in _POL_STOP and not (i > 0 and w[0].isupper()):
            out.add(_stem(w.lower()))
    return out


_NEG_CLAUSE = re.compile(r"\b(?:not|no|never|none|neither|nor|without|cannot|unable|denied|denies|refused|declined|failed\s+to)\b|n't\b|\b(?:un(?:confirmed|verified|clear|known))\b", re.IGNORECASE)

# A claim that uses one of these state/outcome/promise/universality predicates must find it, un-negated, in the evidence it leans on.
_PRED = (
    ("ongoing", re.compile(r"\b(?:ongoing|continu\w+|persist\w*|unresolved|still\s+(?:ongoing|affect\w+|down|unavailable|occurring|happening)|remains?\s+(?:ongoing|unresolved|down|unavailable))\b", re.IGNORECASE),
     re.compile(r"\b(?:ongoing|continu\w+|persist\w*|unresolved|still|remain\w*|investigating|underway|under\s+way|restoring|being\s+restored|crews\s+are|engineers\s+are|working\s+to)\b", re.IGNORECASE)),
    ("resolved", re.compile(r"\b(?:resolved|restored|recovered|resumed|fixed|rectified|remediated|mitigated|contained|stabili[sz]ed|ended|back\s+(?:online|to\s+normal)|returned\s+to\s+normal|has\s+restored|have\s+restored)\b", re.IGNORECASE),
     re.compile(r"\b(?:resolv\w+|restor\w+|recover\w*|resum\w+|fix\w*|rectif\w+|remediat\w+|mitigat\w+|contain\w*|stabili[sz]\w+|ended|back\s+(?:online|to\s+normal)|returned\s+to\s+normal|deployed)\b", re.IGNORECASE)),
    ("compensation", re.compile(r"\b(?:compensat\w+|refund\w*|reimburs\w+|make\s+good|credit\s+(?:customers|accounts))\b", re.IGNORECASE),
     re.compile(r"\b(?:compensat\w+|refund\w*|reimburs\w+|make\s+good|credit\w*)\b", re.IGNORECASE)),
    ("promise", re.compile(r"\b(?:will|would|going\s+to|plans?\s+to|planned\s+to|set\s+to|promised|pledged|committed\s+to|vowed|undertook|guarantee\w*)\b", re.IGNORECASE),
     re.compile(r"\b(?:will|would|going\s+to|plans?\s+to|planned|set\s+to|promis\w+|pledg\w+|committed|commit\w*|vow\w*|expected\s+to|due\s+to|scheduled|aims?\s+to|intends?\s+to|guarantee\w*|by\s+\d{1,2}\s+\w+)\b", re.IGNORECASE)),
    ("universal", re.compile(r"\b(?:all\s+of|all\s+(?:its|their|the)?\s*(?:customers|users|clients|services|regions|states|sites|systems)|every(?:one|body)?|entire|whole)\b", re.IGNORECASE),
     re.compile(r"\b(?:all|every(?:one|body)?|entire|whole)\b", re.IGNORECASE)),
    ("extent", re.compile(r"\b(?:nationwide|countrywide|worldwide|globally|across\s+the\s+(?:\w+\s+)?(?:country|sector|industry|nation|state|region|world)|sector[- ]wide|industry[- ]wide|completely|fully|totally)\b", re.IGNORECASE),
     re.compile(r"\b(?:nationwide|countrywide|worldwide|global(?:ly)?|across|sector|industry|complete(?:ly)?|full(?:y)?|total(?:ly)?)\b", re.IGNORECASE)),
    ("trend", re.compile(r"\b(?:becoming|increasingly|deteriorat\w+|worsen\w+|escalat(?:e|es|ed|ing)|escalations?\s+(?:of|in)|surg\w+|trend\w*|more\s+frequent|less\s+reliable|growing|improving)\b", re.IGNORECASE),
     re.compile(r"\b(?:increas\w+|decreas\w+|ris(?:e|ing|en)|grow\w*|fall\w*|fell|down\s+from|up\s+from|fewer|deteriorat\w+|worsen\w+|escalat\w+|surg\w+|trend\w*|improv\w+)\b", re.IGNORECASE)),
)
_FORECAST_HEDGE = re.compile(r"\b(?:may|might|could|possible|possibly|likely|unlikely|potential(?:ly)?|watch\s+for|monitor|if\b|should\s+(?:be\s+)?(?:monitored|watched)|risk\s+of)\b", re.IGNORECASE)


def _predicate_misses(clean: str, chosen: list[_Ev], field_name: str) -> list[str]:
    """Labels of predicate classes the claim uses that no chosen evidence clause supports (un-negated)."""
    if not chosen:
        return []
    ev_clauses = [c for e in chosen for s in e.sents for c in ([s] + _clauses(s))]
    ev_text = " ".join(e.text for e in chosen)
    misses: list[str] = []
    for label, claim_re, ev_re in _PRED:
        if not claim_re.search(clean):
            continue
        if label == "promise" and (_FORECAST_HEDGE.search(clean) or field_name == "forward_watch" and _HEDGE.search(clean)):
            continue                                     # a hedged forecast is analysis, not a factual claim of fact
        claim_neg = bool(_NEG_CLAUSE.search(clean))
        ok = False
        for c in ev_clauses:
            if ev_re.search(c) and (claim_neg or not _NEG_CLAUSE.search(c)):
                ok = True
                break
        if not ok and ev_re.search(ev_text) and label in ("promise",) and not _NEG_CLAUSE.search(ev_text):
            ok = True
        if not ok:
            misses.append(label)
    return misses


_SPEECH_NEG = re.compile(r"\b(?:has|have|had|did|does|do|is|are|was|were)?\s*(?:not|never|yet\s+to|no)\s+(?:yet\s+)?(?:been\s+)?(?:confirm|state|say|said|announce|disclos|comment|respond|verif|acknowledg|releas|publish|explain|specif|provid|identif|address|clarif|detail|name|reveal)\w*\b|"
                         r"\b(?:unconfirmed|unverified|undisclosed|unacknowledged)\b", re.IGNORECASE)


def _speech_negation_only(clause: str) -> bool:
    """True when every negation in the clause is a negated speech act (not confirmed / not said / unverified): a statement about what was NOT said."""
    if not _NEG_CLAUSE.search(clause):
        return False
    return not _NEG_CLAUSE.search(_SPEECH_NEG.sub(" ", clause))


def _polarity_conflict(clean: str, chosen: list[_Ev]) -> str | None:
    """Per CLAUSE polarity: for each claim clause, the best-matching evidence clause(s) must agree on negation. Tied best matches
    that include an agreeing clause are not a conflict (the evidence says both ways, so the claim is supported one way)."""
    ev_clauses = [c for e in chosen for s in e.sents for c in _clauses(s)]
    if not ev_clauses:
        return None
    ev_tok = [(c, _pol_tokens(c)) for c in ev_clauses]
    for cc in _clauses(clean) or [clean]:
        ct = _pol_tokens(cc)
        if len(ct) < 2:
            continue
        scored = [(len(ct & t), c) for c, t in ev_tok]
        top = max(n for n, _ in scored)
        if top < min(2, len(ct)) or (top < 0.6 * len(ct) and top < 4):
            continue
        best = [c for n, c in scored if n == top]
        if _speech_negation_only(cc):
            continue                                        # "X has not confirmed Y" negates the statement, not the reported content
        cneg = bool(_NEG_CLAUSE.search(cc))
        if not any(bool(_NEG_CLAUSE.search(c)) == cneg for c in best):
            return f"negation differs from the evidence clause '{best[0][:80]}'"
    return None


_REASON_AFTER = re.compile(r"\b(?:because(?:\s+of)?|due\s+to|owing\s+to|thanks\s+to|blamed\s+on|attributed\s+to|stem(?:s|med|ming)\s+from|driven\s+by|"
                           r"caused\s+by|triggered\s+by|prompted\s+by|resulted\s+from|result(?:s|ed)?\s+from|the\s+reason\s+(?:is|was))\b", re.IGNORECASE)
_ACTIVE_CUE = re.compile(r"\b(?:caus(?:e|es|ed|ing)|trigger(?:s|ed|ing)|led\s+to|leads?\s+to|prompt(?:s|ed|ing)|sparked|blam(?:e|es|ed|ing)|responsible\s+for|behind)\b", re.IGNORECASE)
_SPEECH = re.compile(r"\b(?:said|says|reported|reports|stated|announced|warned|noted|told|disclosed|revealed|claimed|confirmed|apologi[sz]ed)\b", re.IGNORECASE)


def _entity_words(segment: str) -> set[str]:
    mid, init = _entities(segment)
    return {w.lower() for w in mid + init}


def cause_entities(sentence: str) -> set[str]:
    """Entities a sentence names as the CAUSE: the entities immediately before an active cue (inside the same clause, after any
    speech verb) and those after a reason-after cue ("because", "caused by"). Speakers are not causes."""
    out: set[str] = set()
    for m in _REASON_AFTER.finditer(sentence):
        tail = re.split(r"[,;.]", sentence[m.end():], maxsplit=1)[0]
        out |= _entity_words(tail)
    for m in _ACTIVE_CUE.finditer(sentence):
        if re.match(r"\s+by\b", sentence[m.end():]):
            continue
        head = sentence[:m.start()]
        cut = max([sp.end() for sp in _SPEECH.finditer(head)] + [h.end() for h in re.finditer(r"[,;]", head)] + [0])
        out |= _entity_words(head[cut:])
    return out


def speaker_entities(sentence: str) -> set[str]:
    out: set[str] = set()
    for m in _SPEAKER.finditer(sentence):
        out |= {w.lower() for w in _WORD.findall(m.group(1))}
    return out


_COVERAGE_STMT = re.compile(r"\b(?:sources?|feeds?|publishers?|collection|coverage)\b.*\b(?:checked|available|reported|report|failed|unavailable|unreachable|"
                            r"missing|incomplete|degraded|responded|completed|did\s+not|not\s+report\w*|limited|partial|gaps?)\b|"
                            r"\b(?:checked|failed|unavailable|did\s+not\s+report|not\s+report\w*)\b.*\b(?:sources?|feeds?|publishers?)\b", re.IGNORECASE)
_NO_ITEMS = re.compile(r"\b(?:no|zero|0)\s+(?:items|events|reports|signals|incidents|stories|articles)\s+(?:were\s+|was\s+)?(?:collected|available|reported|found|gathered)\b", re.IGNORECASE)
_RISK_LABEL_RE = re.compile(r"\b(?:RED|AMBER|GREEN|UNKNOWN)\b")


def _check_coverage_claim(text: str, ctx_figs: set[float], ctx_names: set[str], ev_ents: set[str], n_live: int = 0) -> list[tuple[str, str]]:
    """A sentence ABOUT the collection (counts of sources, which ones failed). Checked against the prompt facts only; it can state no
    cause, no attribution and no incident content."""
    out: list[tuple[str, str]] = []
    figs, _ = figures_in(_STD_REF.sub(" ", text))
    for v in figs:
        if v not in ctx_figs:
            out.append(("invented_figure", f"figure {v:g} is not a collection count given in the prompt"))
    mid, init = _entities(text)
    for w in mid + init:
        lw = w.lower()
        if lw not in ctx_names and lw not in ev_ents and _stem(lw) not in ev_ents:
            out.append(("invented_entity", f"'{w}' is not a source named in the prompt"))
    if causal(text) and not _HEDGE.search(text):
        out.append(("unsupported_causal", "a collection statement states a cause"))
    if _NO_ITEMS.search(text) and n_live > 0:
        out.append(("unsupported_fact", f"states that no items were collected but {n_live} exist"))
    return out


_VERBISH = re.compile(r"\b(?:\w+ed|said|says|told|blamed|sued|fined|hit|ran|took|gave|made|caused|led|ordered|opened|closed|warned|accused|charged|attacked|"
                      r"acquired|bought|sold|apologi[sz]ed|reported|announced|confirmed|investigat\w+|notified|referred|sanctioned|penalis\w+|penaliz\w+)\b", re.IGNORECASE)


_CAP_RUN = re.compile(r"\b[A-Z][A-Za-z&'’-]*(?:\s+[A-Z][A-Za-z&'’-]*)*")


def _mentions(sentence: str) -> list[tuple[str, int, int]]:
    """Entity mentions as (key, start, end): runs of capitalised words, keyed by their last word (so 'Health Services Commission' and a later
    'Commission' are the same entity). Leading common words ('The', 'At') are dropped from a run."""
    out = []
    for m in _CAP_RUN.finditer(sentence):
        words = m.group(0).split()
        while words and words[0].lower() in _COMMON_INITIAL:
            words = words[1:]
        if not words:
            continue
        key = re.sub(r"['’]s$", "", words[-1]).lower()
        if len(key) < 3 or key in _ENTITY_ALLOW:
            continue
        out.append((key, m.start(), m.end()))
    return out


def _verb_pairs(sentence: str, keys: set[str]) -> set[tuple[str, str]]:
    ms = [x for x in _mentions(sentence) if x[0] in keys]
    pairs = set()
    for (a, _s1, e1), (b, s2, _e2) in itertools.pairwise(ms):
        if a != b and _VERBISH.search(sentence[e1:s2]):
            pairs.add((a, b))
    return pairs


def _role_swap(claim: str, chosen: list[_Ev]) -> bool:
    """True when the claim has 'A <verb> ... B' between consecutive entity mentions while the evidence only has 'B <verb> ... A' (subject and
    object swapped). Reordering without a verb between the two ("At B, A said ...") is not flagged."""
    ckeys = {x[0] for x in _mentions(claim)}
    if len(ckeys) < 2:
        return False
    cpairs = _verb_pairs(claim, ckeys)
    if not cpairs:
        return False
    for e in chosen:
        for sent in e.sents:
            epairs = _verb_pairs(sent, ckeys)
            for a, b in cpairs:
                if (a, b) not in epairs and (b, a) in epairs:
                    return True
    return False


# ── Round-3 additions: all-field governance, uncertainty form, cause-unknown wording, labels, time of day, verbatim support ──────────

_LABEL_PREFIX = re.compile(r"^\W*(?:[A-Za-z]+\s+){0,3}(?:alert|warning|notice|advisory|update|incident|outage|recall|watch|bulletin)\s*:\s*")
_RISK_SENT = re.compile(r"^\W*(?:the\s+)?(?:overall\s+)?(?:risk|posture|rating|risk\s+rating|risk\s+posture|status)(?:\s+(?:is|was|remains|rating\s+is|level\s+is))?\s*[:=]?\s*(?:is\s+)?(RED|AMBER|GREEN|UNKNOWN)\W*$", re.IGNORECASE)
_NO_ITEMS_TOPIC = re.compile(r"^\W*(?:no|zero)\s+(?:items|events|reports|signals|incidents|stories|articles)\s+(?:for|on|about|matching|relating\s+to|under)\s+(?:the\s+)?(.{1,60}?)(?:\s+(?:topic|domain|category|feed|theme))?\W*$", re.IGNORECASE)

# Generic reassurance and reader-directed instruction. Checked in EVERY narrative field (previously only the snapshot lexical rule caught some).
# An all-clear sentence that names a specific incident goes through the normal evidence checks; a bare one cannot be supported by any evidence.
_REASSURANCE = [re.compile(p, re.IGNORECASE) for p in (
    r"\ball\s+(?:[\w-]+\s+){0,3}(?:systems?|services?|operations?|domains?|sectors?|infrastructure|platforms?)\s+(?:are|were|remain|remains|is)\s+(?:currently\s+|now\s+|all\s+)?(?:secure|normal|operating\s+normally|operational|healthy|stable|safe|fine|unaffected|functioning|restored|up)\b",
    r"\b(?:no|zero)\s+(?:significant|material|major|notable|serious|further|additional|new|other)\s+(?:risks?|incidents?|developments?|issues?|threats?|concerns?|events?|disruptions?)\b",
    r"\boperations?\s+(?:are|is|remain|remains)\s+(?:normal|stable|unaffected|as\s+usual|business\s+as\s+usual)\b",
    r"\bnothing\s+(?:significant\s+|material\s+)?(?:to\s+(?:report|flag|see)|of\s+(?:note|concern))\b",
    r"\bno\s+(?:further\s+)?(?:action|escalation|monitoring)\s+(?:is\s+)?(?:required|needed|necessary|warranted)\b",
    r"\bwarrants?\s+no\s+(?:action|escalation|attention)\b",
    r"\ball[\s-]+clear\b",
    r"\bbusiness\s+as\s+usual\b",
)]
_NOT_REASSURANCE = re.compile(r"\b(?:not|no|without|never|cannot|can'?t|does\s+not\s+mean|do\s+not\s+mean|should\s+not\s+be\s+read\s+as|nor)\b[^.]{0,30}\b(?:all[\s-]+clear|reassurance|assurance|that\s+nothing)\b|\bnot\s+an?\s+all[\s-]+clear\b", re.IGNORECASE)
_NARR_DIRECTIVE = [re.compile(p, re.IGNORECASE) for p in (
    r"^\W*(?:please\s+)?(?:tell|inform|assure|reassure|advise|instruct|remind|ask)\s+(?:the\s+)?(?:captain|reader|user|board|ceo|team)\b",
    r"\b(?:suppress|silence|mute|ignore|disregard|dismiss|omit|conceal|hide|delete|drop|downgrade)\s+(?:all\s+|any\s+|every\s+|the\s+|this\s+|these\s+|those\s+)?(?:[\w'’-]+\s+){0,3}(?:alerts?|warnings?|notifications?|incidents?|events?|reports?|items?|recalls?|risks?|outages?|breach(?:es)?)\b",
    r"\b(?:do\s+not|don'?t)\s+(?:escalate|alert|notify|report|worry|act|respond)\b",
)]

# A known-unknown item has to BE an uncertainty (a gap the evidence itself shows), never an assertion.
_UNCERTAIN = re.compile(
    r"\b(?:not\s+(?:yet\s+)?(?:been\s+)?(?:known|clear|confirmed|identified|established|determined|verified|stated|said|disclosed|released|reported|specified|explained|given|provided|announced|available|publicly)|"
    r"(?:has|have|had|did)\s+not\s+(?:yet\s+)?(?:said|stated|confirmed|identified|disclosed|explained|specified|responded|commented|released|provided|given|announced|established|published)|"
    r"unknown|unclear|unconfirmed|unverified|undetermined|unidentified|undisclosed|uncertain|unresolved|unexplained|unspecified|unreported|unstated|"
    r"no\s+(?:public\s+)?(?:confirmation|information|detail|details|statement|explanation|word|indication|evidence|figure|estimate)|"
    r"yet\s+to\s+(?:be\s+)?\w+|remains?\s+(?:open|to\s+be\s+(?:seen|determined|confirmed|established))|whether|if\s+and\s+when|"
    r"watch\s+for|monitor\s+for|look\s+for|awaiting|await\w*|pending|still\s+(?:to\s+be|unclear|unknown)|could\s+not\s+be\s+(?:confirmed|verified|determined))\b|\?", re.IGNORECASE)
_UNCERT_VOCAB = frozenset(["whether", "remains", "remain", "yet", "pending", "awaiting", "await", "watch", "monitor", "look", "confirmation", "information", "detail", "details", "statement", "explanation", "word", "indication", "evidence", "figure", "estimate", "publicly", "specified", "stated", "said", "disclosed", "released", "explained", "provided", "announced", "established", "determined", "identified", "verified", "reported", "given", "published", "responded", "commented", "seen", "occurred", "occur", "happened", "happen", "exist", "exists", "existed", "real", "true", "took", "place"])
# State words a known-unknowns item may ask about ("whether the fault has been resolved"); the event and entities it is about must still be supported.
_STATE_VOCAB = frozenset(["resolved", "resolve", "restored", "restore", "fixed", "ongoing", "continuing", "continue", "over", "ended", "recovered", "contained", "spread", "worsen", "escalate", "escalated", "resumed", "improved", "stabilised", "stabilized", "finished", "complete", "completed"])

# Wording that says the cause is NOT known / is awaited. Such a sentence asserts no cause (its causal vocabulary is about the gap).
_CAUSE_NOUN = r"(?:cause|causes|reason|reasons|origin|source|trigger|explanation)"
_CAUSE_UNKNOWN = [re.compile(p, re.IGNORECASE) for p in (
    r"\b" + _CAUSE_NOUN + r"\b[^.;!?]{0,60}?\b(?:has\s+|have\s+|is\s+|was\s+|were\s+|are\s+|remains?\s+)?(?:not|never|yet\s+to|still\s+(?:unknown|unclear|unconfirmed)|unknown|unclear|unconfirmed|undetermined|unexplained|unidentified|undisclosed|under\s+investigation|being\s+investigated)\b[^.;!?]*",
    r"\b(?:no|without|unknown|unclear|undisclosed)\s+(?:\w+\s+){0,2}" + _CAUSE_NOUN + r"\b[^.;!?]*",
    r"\bnot\s+(?:yet\s+)?(?:said|stated|explained|disclosed|identified|confirmed|determined|established|released|given|known|clear)\s+(?:what|why|how|the\s+" + _CAUSE_NOUN + r")\b[^.;!?]*",
    r"\b(?:unclear|unknown|not\s+(?:yet\s+)?(?:known|clear))\s+(?:why|what|how|whether)\b[^.;!?]*",
    r"\b(?:watch|look|wait|monitor|await\w*|pending|expect|seek)\w*\s+(?:for\s+)?[^.;!?]{0,25}\b" + _CAUSE_NOUN + r"\b[^.;!?]*",
    r"\b(?:confirmation|identification|determination|disclosure|announcement|explanation)\s+of\s+(?:the\s+)?" + _CAUSE_NOUN + r"\b[^.;!?]*",
    r"\b(?:to|until|before|once|when|if|whether)\s+(?:identify|determine|establish|confirm|find\s+out|work\s+out|explain)\w*\s+(?:the\s+)?" + _CAUSE_NOUN + r"\b[^.;!?]*",
    r"\binvestigat\w+\s+(?:the\s+)?" + _CAUSE_NOUN + r"\b[^.;!?]*",
)]
_WEAK_CAUSE = re.compile(r"\b(?:affecting|affected\s+by|hit\s+by|amid|following|linked\s+to|related\s+to|blamed|struck\s+by)\b", re.IGNORECASE)
_REPORTING_CUE = re.compile(r"\b(?:said|says|stated|named|reported|announced|according\s+to|identified|blamed|attributed|cited|citing|pointed|pointing)\b", re.IGNORECASE)


def _strip_unknown_cause(text: str) -> tuple[str, bool]:
    """(text with the 'cause is not known / awaited' span removed, whether one was found)."""
    out, hit = text, False
    for rx in _CAUSE_UNKNOWN:
        if rx.search(out):
            out, hit = rx.sub(" ", out), True
    return out, hit


def _speaker_aliases(sentence: str, ev: _Ev) -> set[str]:
    """Words that may stand for the speaker(s) of an evidence sentence: the words themselves, the source name, and initialisms (AWS for Amazon Web Services)."""
    out = set(speaker_entities(sentence)) | {w.lower() for w in _WORD.findall(ev.source)}
    for m in _SPEAKER.finditer(sentence):
        words = [w for w in _WORD.findall(m.group(1)) if w.lower() not in ("the", "of", "for", "and")]
        if len(words) >= 2:
            out.add("".join(w[0] for w in words).lower())
    return out




def _check_claim(field_name: str, text: str, evs: list[_Ev], all_ents: set[str], allowed_figs: set[float],
                 allowed_dates: set[tuple[int, int]], url_ok: set[str], *, ctx_figs: set[float] | None = None,
                 ctx_names: set[str] | None = None, allowed_weekdays: set[str] | None = None,
                 ctx_risk: str | None = None) -> list[ClaimFailure]:
    fails: list[ClaimFailure] = []
    ctx_figs = ctx_figs or set()
    ctx_names = ctx_names or set()

    def fail(kind: str, detail: str) -> None:
        if not any(f.kind == kind for f in fails):
            fails.append(ClaimFailure(kind, text[:240], detail))

    clean = clean_text(text)
    if has_control_chars(text):
        fail("hostile_content", "control, invisible or direction-override characters in the text")
    if hostile_hits(clean):
        fail("hostile_content", "instruction-like or markup content in narrative")
    if _TAG.search(clean) or re.search(r"\]\(", clean):
        fail("hostile_content", "markup or link syntax in narrative")
    for ev in evs:   # echo of instruction-like source text
        if ev.hostile:
            for s in ev.sents:
                ts, tc = _content_stems(s), _content_stems(clean)
                if hostile_hits(s) and ts and tc and (len(ts & tc) / len(ts | tc) >= 0.5 or (len(tc) >= 2 and len(ts & tc) / len(tc) >= 0.7)):
                    fail("hostile_content", "narrative repeats instruction-like source text")
    if field_name not in _ADVICE_FIELDS:
        if any(rx.search(clean) for rx in _NARR_DIRECTIVE):
            fail("hostile_content", "instruction addressed to the reader (suppress, ignore, tell the Captain)")
        if any(rx.search(clean) for rx in _REASSURANCE) and not _NOT_REASSURANCE.search(clean):
            m_ent, m_init = _entities(clean)
            f0, _i0 = figures_in(clean)
            if not (m_ent or m_init or f0):
                fail("unsupported_fact", "bare reassurance or all-clear statement: no evidence can support it")
    clean = _LABEL_PREFIX.sub("", clean) or clean

    # citations ---------------------------------------------------------------------------------------------------
    cite_names: list[str] = []
    for m in _URL.finditer(clean):
        if _norm_url(m.group(0)) not in url_ok:
            fail("fabricated_citation", "link that is not in the evidence")
    by_id = {e.id.lower(): e for e in evs}
    inline: list[_Ev] = []
    for m in _INLINE_REF.finditer(clean):
        ref = m.group(1).lower()
        ev = by_id.get(ref) or by_id.get(f"e{ref}")
        if ev is None:
            fail("fabricated_citation", f"reference [{m.group(1)}] does not exist")
        else:
            inline.append(ev)
    for m in _CITE_STYLE.finditer(text):
        cite_names.append(m.group(1).strip())

    scan = _INLINE_REF.sub(" ", _URL.sub(" ", clean))
    rl = _RISK_SENT.match(scan)
    if rl:
        label = rl.group(1).upper()
        given = str(ctx_risk or "").upper()
        live_risks = {e.risk for e in evs if not e.hostile and e.risk}
        if given and label != given:
            fail("unsupported_fact", f"risk label {label} differs from the brief's computed overall risk {given}")
        elif not given and label == "GREEN":
            fail("unsupported_fact", "a GREEN risk label cannot be supported without the brief's computed risk")
        elif not given and live_risks and label not in live_risks and label != "UNKNOWN" and (label == "GREEN" or "RED" in live_risks and label != "RED"):
            fail("unsupported_fact", "risk label is lower than the evidence's own ratings")
        return fails
    nt = _NO_ITEMS_TOPIC.match(scan)
    if nt and not cite_names:
        topic_words = [w.lower() for w in _WORD.findall(nt.group(1)) if len(w) >= 3 and w.lower() not in _SKIP and w.lower() not in _COMMON_INITIAL]
        if any(w in e.ents or _stem(w) in e.ents for w in topic_words for e in evs if not e.hostile):
            fail("unsupported_fact", "states there are no items on a topic the evidence does mention")
        return fails
    is_cov = bool(_COVERAGE_STMT.search(scan) or _NO_ITEMS.search(scan)) and not cite_names and not _SPEAKER.search(scan)
    if is_cov:
        # A statement about the collection itself: checked against the prompt facts, not against incident evidence.
        for kind, detail in _check_coverage_claim(scan, ctx_figs | {float(len(evs))}, ctx_names, all_ents, len([e for e in evs if not e.hostile])):
            fail(kind, detail)
        return fails

    # A sentence that IS a sentence of a (non-quarantined) evidence item is the evidence's own wording: nothing in it can be unsupported.
    # (Instruction-like shape is excluded so a paraphrased directive in a source cannot be relayed as a verbatim claim.)
    if not fails and not _DIRECTIVE_SHAPE.search(scan) and len(_norm_sentence(scan).split()) >= 3:
        nsent = _norm_sentence(scan)
        if any(nsent in e.norm_sents for e in evs if not e.hostile):
            return fails
    ents_mid, ents_init = _entities(scan)
    cited_words = {w.lower() for c in cite_names for w in _WORD.findall(c)}
    in_corpus_names = [c for c in cite_names if any(_has_word(e, c) for e in evs if not e.hostile)]
    for c in cite_names:
        if c not in in_corpus_names:
            fail("fabricated_citation", f"cited publisher '{c}' is not among the evidence sources")

    # entities -----------------------------------------------------------------------------------------------------
    ents_l = []
    for w in ents_mid + ents_init:
        lw = w.lower()
        if lw in cited_words:
            continue
        known = lw in all_ents or _stem(lw) in all_ents
        if not known and "-" in w:
            caps = [x.lower() for x in w.split("-") if x[:1].isupper() and len(x) > 1]
            known = bool(caps) and all(x in all_ents or _stem(x) in all_ents for x in caps)
        if not known:
            fail("invented_entity", f"'{w}' is not in the evidence")
        else:
            ents_l.append(lw)

    # figures, dates, weekdays ---------------------------------------------------------------------------------------
    figs, ids = figures_in(_STD_REF.sub(" ", scan))
    dts, _ = dates_in(scan)
    ev_ids = set().union(*[e.ids for e in evs]) if evs else set()
    for i in ids:
        if i not in ev_ids:
            fail("invented_figure", f"identifier {i} is not in the evidence")
    for v in figs:
        if not any(abs(v - a) <= max(1e-6, abs(a) * 0.005) for a in allowed_figs):
            fail("invented_figure", f"figure {v:g} is not in the evidence")
    for m in _LARGE_Q.finditer(scan):
        need = _LARGE_MIN.get(re.sub(r"\s+", " ", m.group(1).lower()), 0)
        if not any(a >= need for a in allowed_figs):
            fail("invented_figure", f"'{m.group(0).strip()}' implies a magnitude the evidence does not give")
    for d in dts:
        if d not in allowed_dates:
            fail("invented_date", f"date {d[1]}/{d[0]} is not in the evidence")
    for m in _WEEKDAY_RE.finditer(scan):
        if allowed_weekdays is not None and m.group(1).lower() not in allowed_weekdays:
            fail("invented_date", f"weekday {m.group(1)} is not in the evidence")

    live_ev = [e for e in evs if not e.hostile]
    claim_times, _ = times_in(scan)
    if claim_times:
        ev_times = set().union(*[e.times for e in live_ev]) if live_ev else set()
        for t in sorted(claim_times):
            if t not in ev_times:
                fail("invented_date", f"time of day {t // 60:02d}:{t % 60:02d} is not in the evidence")
    claim_parts = dayparts_in(scan)
    if claim_parts:
        ev_parts = set().union(*[e.dayparts for e in live_ev]) if live_ev else set()
        ev_part_times = {daypart_of_minute(t) for e in live_ev for t in e.times}
        if (ev_parts or ev_part_times) and not (claim_parts & (ev_parts | ev_part_times)):
            fail("invented_date", "part of the day differs from the evidence")

    advice = field_name in _ADVICE_FIELDS
    is_ku = field_name == "known_unknowns"
    if is_ku and not _UNCERTAIN.search(scan):
        fail("unsupported_fact", "known-unknowns item is stated as fact, not as an uncertainty the evidence shows")

    # lexical support ----------------------------------------------------------------------------------------------
    ent_words = {w.lower() for w in ents_mid + ents_init}
    stems = _content_stems(_STD_REF.sub(" ", scan), exclude=ent_words | cited_words
                           | (_stem_set(_ANALYSIS_VOCAB) if (field_name in LIST_FIELDS and not is_ku) else set())
                           | (_stem_set(_UNCERT_VOCAB | _STATE_VOCAB) if is_ku else set()))
    # A claim with essentially no checkable content cannot be called supported (degenerate / padding sentences).
    if (len(stems) + len(ents_l) + len(figs) + len(dts)) < (1 if is_ku else 2) and not advice:
        fail("unsupported_fact", "no checkable content in the sentence")
    coordinated = bool(re.search(r"\b(?:and|while|both|but|alongside|whereas)\b|[;]", clean, re.IGNORECASE))
    live_evs = [e for e in evs if not e.hostile]
    if advice:
        chosen, covered = list(live_evs), set()
        lexical_ok = True
    else:
        chosen, covered = _pick_support(stems, ents_l, evs, coordinated=coordinated)
        unsupported = stems - covered
        max_frac = STRICT_MAX_UNSUPPORTED if (field_name in _STRICT_FIELDS or is_ku) else RELAXED_MAX_UNSUPPORTED
        allowed_missing = int(max_frac * len(stems)) if stems else 0
        lexical_ok = (not stems) or (len(unsupported) <= allowed_missing and (field_name in _STRICT_FIELDS or covered or not stems))
    pol_text, unknown_cause = _strip_unknown_cause(clean)       # "the cause is not known / awaited" asserts no cause
    is_causal = causal(pol_text) if unknown_cause else causal(clean)
    if stems and not lexical_ok:
        fail("unsupported_causal" if is_causal else "unsupported_fact",
             f"not supported by the evidence: {', '.join(sorted(unsupported))[:120]}")
    if not chosen and (stems or advice):
        if not any(f.kind in ("unsupported_fact", "unsupported_causal") for f in fails):
            fail("unsupported_fact", "no supporting evidence")
        return fails

    # state / outcome / promise / universality predicates must be in the evidence the claim leans on -------------------------------
    pred_scope = chosen if not advice else live_evs
    for label in ([] if (is_ku and _UNCERTAIN.search(scan)) else _predicate_misses(clean, pred_scope, field_name)):
        fail("unsupported_causal" if (label in ("compensation", "promise") and is_causal) else "unsupported_fact",
             f"claim states '{label}' which the supporting evidence does not")

    # "X but not Y" in the evidence: a claim that AFFIRMS Y (outside any negation of its own) contradicts it.
    if chosen and not advice:
        ev_neg = set().union(*[e.neg_stems for e in chosen])
        ev_aff = set().union(*[e.aff_stems for e in chosen])
        claim_aff: set[str] = set()
        for cl in ([c.strip() for c in _CLAUSE_COARSE.split(pol_text) if c and c.strip()] or [pol_text]):
            if _NEG_CLAUSE.search(cl):
                continue                                    # a clause that is itself negated (before or after the words) is not an affirmation
            claim_aff |= _content_stems(cl, exclude=ent_words | cited_words) - negation_scope_stems(cl)
        clash = sorted((claim_aff & (ev_neg - ev_aff)) - {w for w in claim_aff if w in _stem_set(_UNCERT_VOCAB)})
        if clash and not _UNCERTAIN.search(scan):
            fail("unsupported_fact", f"claim affirms '{clash[0]}', which the evidence states only in the negative")

    if stems and not advice:
        best = _best_single(stems, evs)
    elif ents_l and not advice:
        cands = [e for e in live_evs if any(w in e.ents for w in ents_l)]
        best = max(cands, key=lambda e: sum(w in e.ents for w in ents_l)) if cands else None
    else:
        best = chosen[0] if chosen else None

    # coherence: entities / figures / dates must belong with the content they are attached to ---------------------------
    if best is not None and ents_l and not coordinated and lexical_ok and not advice:
        missing = [w for w in ents_l if w not in best.ents]
        if missing:
            fail("misattribution", f"'{missing[0]}' is not part of the story the rest of the claim is drawn from")
    if ents_l:
        owners = [e for e in evs if not e.hostile and any(w in e.ents for w in ents_l)]
        for v in figs:
            holders = [e for e in evs if not e.hostile and any(abs(v - a) <= abs(a) * 0.005 + 1e-6 for a in e.figs)]
            if holders and owners and not set(map(id, holders)) & set(map(id, owners)):
                fail("misattribution", f"figure {v:g} belongs to a different story than the entities named")
        for d in dts:
            holders = [e for e in evs if not e.hostile and d in e.dates]
            if holders and owners and not set(map(id, holders)) & set(map(id, owners)):
                fail("misattribution", "date belongs to a different story than the entities named")
        for t in claim_times:
            holders = [e for e in evs if not e.hostile and t in e.times]
            if holders and owners and not set(map(id, holders)) & set(map(id, owners)):
                fail("misattribution", "time of day belongs to a different story than the entities named")
    if chosen and not advice and _role_swap(scan, chosen):
        fail("misattribution", "who did what to whom is reversed relative to the evidence")

    # attribution targets ------------------------------------------------------------------------------------------
    speakers = [m.group(1).strip() for m in _SPEAKER.finditer(text)]
    for who in speakers + [c for c in cite_names if c in in_corpus_names]:
        holders = [e for e in evs if not e.hostile and _has_word(e, who)]
        if not holders:
            continue
        cov = set().union(*[e.stems for e in holders]) if holders else set()
        if stems and len(stems & cov) / len(stems) < 0.6:
            fail("misattribution", f"'{who}' is credited with content their reporting does not contain")
    if speakers and stems and not advice:
        # the speaker of the best-matching evidence sentence must be the speaker named in the claim
        ev_sent = max(((e, s2) for e in chosen for s2 in e.sents), key=lambda x: len(stems & _content_stems(x[1])), default=None)
        if ev_sent is not None and len(stems & _content_stems(ev_sent[1])) >= max(2, int(0.4 * len(stems))):
            ev_speakers = _speaker_aliases(ev_sent[1], ev_sent[0]) if speaker_entities(ev_sent[1]) else set()
            claim_speakers = {w.lower() for sp in speakers for w in _WORD.findall(sp)}
            if ev_speakers and claim_speakers and not (claim_speakers & ev_speakers):
                fail("misattribution", "the statement is credited to a different speaker than in the evidence")
    for ev in inline:
        if stems and len(stems & ev.stems) / len(stems) < 0.5:
            fail("misattribution", f"cited item {ev.id} does not contain the claim")

    # causal -------------------------------------------------------------------------------------------------------
    hedged_claim = bool(_HEDGE.search(clean)) or unknown_cause
    if is_causal and not hedged_claim:
        weak_ok = bool(_REPORTING_CUE.search(clean))        # "congestion is cited as the reason": an attributed reason may rest on "X said congestion was affecting Y"
        stating = [e for e in chosen if any(causal(s) or (weak_ok and _WEAK_CAUSE.search(s)) for s in e.sents)]
        if not stating:
            fail("unsupported_causal", "no evidence states a cause")
        else:
            clause = _cue_clause(clean)
            cstems = _content_stems(clause, exclude=ent_words | cited_words)
            cs = set()
            for e in stating:
                for s in e.sents:
                    if causal(s) or (weak_ok and _WEAK_CAUSE.search(s)):
                        cs |= _content_stems(s)
            if cstems and len(cstems & cs) / len(cstems) < 0.6:
                fail("unsupported_causal", "the stated cause differs from the cause in the evidence")
            # role check: every entity the claim names as a cause must be named as a cause (not merely as a speaker) in the evidence
            claim_causes = cause_entities(scan) - cited_words
            if claim_causes:
                ev_causes: set[str] = set()
                for e in stating:
                    for s in e.sents:
                        if causal(s):
                            ev_causes |= cause_entities(s)
                if ev_causes and not claim_causes <= (ev_causes | {_stem(w) for w in ev_causes}):
                    fail("unsupported_causal", f"role mismatch: '{min(claim_causes - ev_causes)}' is not named as the cause in the evidence")
            fams = {e.family for e in stating if e.kind != AGGREGATOR}
            reporting = bool(_REPORTING_CUE.search(clean))
            attributed = reporting and (any(any(_has_word(e, who) for e in stating) for who in speakers + cite_names)
                                        or any(w in e.ents for e in stating for w in ents_l))
            primary = any(e.kind == PRIMARY for e in stating)
            if not (len(fams) >= 2 or primary or attributed):
                fail("unsupported_causal", "cause asserted as fact from fewer than two independent sources")
    if advice:
        return fails

    # certainty vs evidence --------------------------------------------------------------------------------------------
    scrub = _NEG_CONFIRM.sub(" ", clean)
    strong = bool(_STRONG.search(scrub))
    if stems:
        sent_pool = [(e, s) for e in chosen for s in e.sents]
        relevant = [(e, s) for e, s in sent_pool if len(stems & _content_stems(s)) >= max(1, int(0.4 * len(stems)))]
        if not relevant and best is not None:
            relevant = [(best, s) for s in best.sents[:1]]
        unhedged = [(e, s) for e, s in relevant if not _HEDGE.search(s)]
        pol = _polarity_conflict(pol_text if unknown_cause else clean, chosen)
        if pol:
            fail("unsupported_fact", f"polarity differs from the evidence ({pol})")
        if strong:
            affirmed = any(_AFFIRM.search(s) for e, s in unhedged)
            if not unhedged or not affirmed:
                fail("uncertainty_misrepresented", "claim asserts certainty the evidence does not give")
        if _MULTI_SOURCE.search(clean):
            fams = {e.family for e, s in unhedged if e.kind != AGGREGATOR}
            if len(fams) < 2:
                fail("uncertainty_misrepresented", "claims multiple sources but evidence has fewer than two independent")
        if field_name in _STRICT_FIELDS and relevant and not unhedged and not hedged_claim and not strong:
            fail("uncertainty_misrepresented", "evidence is unconfirmed or hedged but the claim states it as fact")
    return fails


def _cue_clause(text: str) -> str:
    for part in re.split(r",|;|\band\b|\bbut\b|\bwhile\b", text):
        if causal(part):
            return part
    return text


def validate_narrative(narrative: dict, evidence: list[dict], *, mode: str = "shadow",
                       context: dict | None = None) -> ClaimGateResult:
    """Gate a generated narrative against the evidence it was written from.

    ``narrative``: the six narrative fields (+ optional ``evidence_refs``). ``evidence``: dicts with id/title/summary/source and
    optionally canonical_url. ``context``: optional prompt facts that may legitimately appear (period dates, source counts,
    names of failed sources). Never raises: an internal error is a failed gate (fail closed)."""
    if mode not in ("shadow", "enforce"):
        raise ValueError(f"mode must be 'shadow' or 'enforce', got {mode!r}")
    try:
        return _validate(narrative, evidence, mode, context or {})
    except Exception as exc:  # noqa: BLE001 - fail closed: a gate that cannot decide has not passed the narrative
        log.warning("claim gate error (treated as failed): %s", exc)
        return ClaimGateResult(False, mode, 0, 0, [ClaimFailure("unsupported_fact", "", "gate_error")], reasons=[f"gate_error:{type(exc).__name__}"])


def _allowed_facts(evs: list[_Ev], context: dict):
    """(entity words, figures, dates, urls) the EVIDENCE allows, plus prompt-context figures/names/weekdays kept SEPARATE: context may
    only back sentences about the collection, never an incident claim (a coincidence with a source count is not support)."""
    live = [e for e in evs if not e.hostile]
    all_ents: set[str] = set()
    allowed_figs: set[float] = set()
    allowed_dates: set[tuple[int, int]] = set()
    url_ok: set[str] = set()
    weekdays: set[str] = set()
    for e in live:
        all_ents |= e.ents
        allowed_figs |= e.figs
        allowed_dates |= e.dates
        url_ok |= e.urls
        weekdays |= {m.group(1).lower() for m in _WEEKDAY_RE.finditer(e.text)}
    ctx_text = " ".join(str(v) for k, v in context.items() if k != "missing_sources") + " " + " ".join(map(str, context.get("missing_sources") or []))
    cw = {w.lower() for w in _WORD.findall(ctx_text)}
    ctx_names = cw | {_stem(w) for w in cw}
    ctx_dates = dates_in(ctx_text)[0]
    allowed_dates |= ctx_dates
    ctx_figs, _ = figures_in(ctx_text)
    for k in ("sources_available", "sources_failed", "sources_checked"):
        if isinstance(context.get(k), (int, float)):
            ctx_figs.add(float(context[k]))
    # weekdays of dates the EVIDENCE gives (ISO dates); the prompt period is not a source of weekdays
    import datetime as _dt
    for src in [e.text for e in live]:
        for m in _DATE_ISO.finditer(src):
            try:
                weekdays.add(_WEEKDAYS[_dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).weekday()])
            except ValueError:
                pass
    for e in live:
        weekdays |= e.weekdays
    return all_ents, allowed_figs, allowed_dates, url_ok, ctx_figs, ctx_names, weekdays


def validate_text(text: str, evidence: list[dict], *, field: str = "so_what", mode: str = "enforce",
                  context: dict | None = None) -> ClaimGateResult:
    """Gate ONE generated text surface (e.g. an incident-level ``so_what``, a digest paragraph, a weekly summary) against the evidence
    it was written from. ``field='so_what'`` is advice: structural checks (hostile, links, invented entities/figures/dates/weekdays,
    citations), state/promise predicates and unsupported causal statements; other field names get the full narrative checks. Never
    raises; an internal error is a failed gate."""
    try:
        evs = _build_evidence(evidence)
        if not isinstance(text, str) or not text.strip():
            return ClaimGateResult(False, mode, 0, 0, [ClaimFailure("unsupported_fact", "", "empty text")], reasons=["empty_text"])
        if len(text) > MAX_STR_LEN:
            return ClaimGateResult(False, mode, 0, 0, [ClaimFailure("unsupported_fact", "", "text too long")], reasons=["oversized"])
        claims = [(field, s) for s in _sentences(text)] or [(field, text.strip())]
        allowed = _allowed_facts(evs, context or {})
        failures: list[ClaimFailure] = []
        supported = 0
        for fname, sent in claims[:MAX_CLAIMS]:
            cf_ = _check_claim(fname, sent, evs, *allowed[:4], ctx_figs=allowed[4], ctx_names=allowed[5], allowed_weekdays=allowed[6],
                           ctx_risk=(context or {}).get("overall_risk"))
            if cf_:
                failures.extend(cf_)
            else:
                supported += 1
        failures = failures[:60]
        return ClaimGateResult(not failures, mode, len(claims), supported, failures,
                               fabricated_citations=sum(1 for f in failures if f.kind == "fabricated_citation"),
                               unsupported_causal=sum(1 for f in failures if f.kind == "unsupported_causal"),
                               reasons=[] if not failures else ["claim_gate_failed"])
    except Exception as exc:  # noqa: BLE001 - fail closed
        log.warning("claim gate text error (treated as failed): %s", exc)
        return ClaimGateResult(False, mode, 0, 0, [ClaimFailure("unsupported_fact", "", "gate_error")], reasons=[f"gate_error:{type(exc).__name__}"])


def _validate(narrative: dict, evidence: list[dict], mode: str, context: dict) -> ClaimGateResult:
    if not isinstance(narrative, dict):
        return ClaimGateResult(False, mode, 0, 0, [ClaimFailure("unsupported_fact", "", "narrative is not an object")], reasons=["schema"])
    evs = _build_evidence(evidence)
    claims, problems = _claims_of(narrative)
    failures: list[ClaimFailure] = list(problems)
    reasons: list[str] = ["schema"] if problems else []
    if len(claims) > MAX_CLAIMS:
        failures.append(ClaimFailure("unsupported_fact", "", "too many claims"))
        reasons.append("oversized")
        claims = claims[:MAX_CLAIMS]
    if not claims and not problems:
        return ClaimGateResult(False, mode, 0, 0, [ClaimFailure("unsupported_fact", "", "empty narrative")], reasons=["empty_narrative"])

    # whole-narrative checks
    refs = narrative.get("evidence_refs")
    if refs is not None:
        known = {e.id.lower(): e for e in evs}
        if not isinstance(refs, list):
            failures.append(ClaimFailure("fabricated_citation", "evidence_refs", "references are not a list"))
        else:
            for r in refs:
                ev = known.get(str(r).lower())
                if ev is None:
                    failures.append(ClaimFailure("fabricated_citation", str(r)[:80], "reference does not exist in the evidence"))
                elif ev.hostile:
                    failures.append(ClaimFailure("hostile_content", str(r)[:80], "cites a quarantined source item"))
    for f in LIST_FIELDS + STRING_FIELDS:
        v = narrative.get(f)
        blob = " ".join(v) if isinstance(v, list) and all(isinstance(x, str) for x in v) else v
        if isinstance(blob, str) and hostile_hits(blob):
            parts = v if isinstance(v, list) else [v]
            if not any(isinstance(x, str) and hostile_hits(x) for x in parts):      # split across items: attributable to no single item
                failures.append(ClaimFailure("hostile_content", f, "instruction-like or markup content in narrative", f))
    extra = set(narrative) - ALLOWED_KEYS
    if extra:
        failures.append(ClaimFailure("unsupported_fact", "", f"unexpected keys: {sorted(extra)[:3]}"))
        reasons.append("schema")

    allowed = _allowed_facts(evs, context)
    supported = 0
    for fname, sent, idx in claims:
        cf_ = _check_claim(fname, sent, evs, *allowed[:4], ctx_figs=allowed[4], ctx_names=allowed[5], allowed_weekdays=allowed[6],
                           ctx_risk=(context or {}).get("overall_risk"))
        if cf_:
            for f_ in cf_:
                f_.field, f_.item = fname, idx
            failures.extend(cf_)
        else:
            supported += 1
    if any(e.hostile for e in evs):
        reasons.append("quarantined_source_items")
    failures = failures[:60]
    passed = not failures
    return ClaimGateResult(
        passed=passed, mode=mode, claims_total=len(claims), claims_supported=supported, failures=failures,
        fabricated_citations=sum(1 for f in failures if f.kind == "fabricated_citation"),
        unsupported_causal=sum(1 for f in failures if f.kind == "unsupported_causal"),
        reasons=reasons + ([] if passed else ["claim_gate_failed"]))


# ── Strict output parsing (replaces regex-from-first-brace trust) ──────────────────────────────────────────────

class _Narrative(dict):
    """A plain dict (compares equal to one) that also remembers how many strings had control or invisible characters removed."""
    control_chars_stripped = 0


def parse_narrative_json(raw: object) -> tuple[dict | None, str]:
    """Parse model output as exactly one JSON object with the narrative schema. Returns (narrative, "") or (None, reason).
    Accepts an optional single code fence and surrounding whitespace, nothing else."""
    if not isinstance(raw, str) or not raw.strip():
        return None, "empty"
    s = raw.strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", s, re.DOTALL | re.IGNORECASE)
    if m:
        s = m.group(1)
    try:
        data = json.loads(s)
    except ValueError:
        return None, "not_json"
    if not isinstance(data, dict):
        return None, "not_object"
    if set(data) - ALLOWED_KEYS:
        return None, "unexpected_keys"
    out = _Narrative()
    stripped = 0

    def _clean(x: str) -> str:
        nonlocal stripped
        if has_control_chars(x):
            stripped += 1
            x = strip_control_chars(x)
        return x.strip()
    for f in STRING_FIELDS:
        v = data.get(f)
        if v is None:
            out[f] = None
        elif isinstance(v, str) and len(v) <= MAX_STR_LEN:
            out[f] = _clean(v) or None
        else:
            return None, f"bad_{f}"
    for f in LIST_FIELDS:
        v = data.get(f)
        if v is None:
            out[f] = []
        elif isinstance(v, list) and len(v) <= MAX_LIST_ITEMS and all(isinstance(x, str) and len(x) <= MAX_ITEM_LEN for x in v):
            out[f] = [c for c in (_clean(x) for x in v) if c]
        else:
            return None, f"bad_{f}"
    refs = data.get("evidence_refs")
    if refs is not None:
        if not isinstance(refs, list) or len(refs) > 40:
            return None, "bad_evidence_refs"
        out["evidence_refs"] = [str(r)[:40] for r in refs]
    if not (out["executive_snapshot"] or out["bottom_line"]):
        return None, "no_narrative_text"
    out.control_chars_stripped = stripped
    return out, ""


GATE_REV = 3     # bump when generation-side governance changes: in enforce, rows written by an older gate are not trusted at display
_FIELD_ORDER = ("executive_snapshot", "bottom_line", "emerging_themes", "forward_watch", "cps230_implications", "known_unknowns")


def display_sha(snapshot, bottom_line, themes, forward_watch, cps230, known_unknowns) -> str:
    """Hash of the six stored narrative fields exactly as published. Recorded at generation and re-computed at display, so a coverage record
    cannot vouch for text it was not written for (an edited row, or a record copied onto another row)."""
    def norm(v):
        if isinstance(v, list):
            return [str(x) for x in v]
        return [] if v in (None, "") else v
    payload = json.dumps([snapshot or None, bottom_line or None, norm(themes) or [], norm(forward_watch) or [], norm(cps230) or [],
                          norm(known_unknowns) or []], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


WITHHELD_NOTE = "{n} generated item(s) in the analytical lists were withheld because they could not be checked against the evidence."


def failed_list_items(result: ClaimGateResult) -> dict[str, set[int]] | None:
    """When EVERY failure sits on one list item (``emerging_themes``, ``forward_watch``, ``cps230_implications``, ``known_unknowns``), the items to
    remove, else None (the narrative as a whole must be replaced). The caller must re-validate the remainder: removal is only ever allowed when
    what is left passes the gate on its own."""
    out: dict[str, set[int]] = {}
    for f in result.failures:
        if f.field in LIST_FIELDS and f.item >= 0:
            out.setdefault(f.field, set()).add(f.item)
        else:
            return None
    return out or None


def withhold_items(narrative: dict, drop: dict[str, set[int]]) -> tuple[dict, int]:
    """Copy of the narrative without the given list items; returns (copy, number removed)."""
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in narrative.items()}
    n = 0
    for f, idxs in drop.items():
        items = out.get(f) or []
        keep = [x for i, x in enumerate(items) if i not in idxs]
        n += len(items) - len(keep)
        out[f] = keep
    return out, n


def record_for_coverage(result: ClaimGateResult, narrative: dict | None, *, fallback_used: bool, generated_at: str,
                        published: dict | None = None, items_withheld: int = 0) -> dict:
    """Namespaced, size-bounded record for ``coverage['claim_gate_v1']``. Holds no narrative or source text (hashes and counts
    only), so nothing personal or hostile is stored. ``published`` (the six fields as stored) binds the record to that text (``display_sha``)."""
    h = hashlib.sha256(json.dumps(narrative, sort_keys=True, default=str).encode()).hexdigest()[:16] if narrative else None
    rec = {
        "schema": 1, "published": False, "kind": "claim_gate", "generated_at": generated_at, "mode": result.mode, "gate_rev": GATE_REV,
        "passed": result.passed, "claims_total": result.claims_total, "claims_supported": result.claims_supported,
        "fabricated_citations": result.fabricated_citations, "unsupported_causal": result.unsupported_causal,
        "failure_kinds": sorted({f.kind for f in result.failures}), "failure_count": len(result.failures),
        "failures": [{"kind": f.kind, "claim_sha": hashlib.sha256(f.claim.encode()).hexdigest()[:12]} for f in result.failures[:20]],
        "reasons": result.reasons[:6], "narrative_sha": h, "fallback_used": bool(fallback_used),
        "items_withheld": int(items_withheld),
        "narrative_published": bool(result.passed or result.mode != "enforce" or items_withheld),
    }
    if published is not None:
        rec["display_sha"] = display_sha(*(published.get(k) for k in _FIELD_ORDER))
    return rec
