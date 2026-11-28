#!/usr/bin/env python3
"""Second, deliberately over-inclusive name finder, run inside the guardrails virtualenv (spaCy only, no network).
stdin: JSON list of texts. stdout: {"person": [...], "caps": [...]}, one span list per text. `person` holds positive detections (model
or personal title) and must never be filtered; `caps` holds runs of capitalised words, which only be names."""
import json
import re
import sys

import spacy

ORG_WORDS = {"authority", "bank", "board", "committee", "council", "commission", "department", "ministry", "government", "treasury", "parliament", "court", "tribunal", "institute", "association", "agency", "office", "group", "limited", "ltd", "pty", "fund", "insurer", "insurers", "super", "superannuation", "reserve", "prudential", "regulation", "regulatory", "standard", "standards", "guidance", "guide", "consultation", "report", "reporting", "statistics", "policy", "practice", "framework", "act", "code", "release", "releases", "paper", "letter", "media", "speech", "statement", "minutes", "meeting", "quarterly", "annual", "monthly", "australian", "australia", "asian", "pacific", "international", "national", "federal", "state", "financial", "services", "service", "system", "payments", "risk", "management", "liquidity", "capital", "insurance", "deposit", "credit", "housing", "lending", "market", "markets", "monetary", "operational", "resilience", "cyber", "information", "security", "data", "review", "plan", "program", "programme", "survey", "index", "rate", "rates", "update", "notice", "forum", "conference", "january", "february", "july", "september", "october", "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "apra", "rba", "asic", "accc", "austrac", "basel", "apg", "cps", "cpg", "sps", "lps", "gps", "hps", "new", "the", "a", "an", "of", "on", "for", "to", "and", "in", "at", "by", "with", "from", "its", "this", "that", "chair", "deputy", "governor", "treasurer", "member", "minister", "president", "secretary", "commissioner", "director", "executive", "chief", "officer", "head", "assistant", "general", "managing", "entities", "entity", "banking", "industry", "sector", "customers", "consumers", "submissions", "feedback", "inquiries", "enquiries", "record", "notes", "note", "event", "incident", "story", "profile", "outcome", "action", "penalty", "departure"}
TITLED = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Professor|Prof|Sir|Dame|Hon)\.? +((?:[A-Z][\w'’-]+)(?: +[A-Z][\w'’-]+){0,3})")
CAPS = re.compile(r"\b[A-Z][a-zà-öø-ÿ'’]+(?:[-'’][A-Z]?[a-z]+)*(?: +(?:[A-Z][a-zà-öø-ÿ]*[-'’])?[A-Z][a-zà-öø-ÿ'’]+(?:-[A-Z][a-z]+)*){1,3}")


def spans(doc):
    text = doc.text
    person = [(e.start_char, e.end_char) for e in doc.ents if e.label_ == "PERSON"] + [m.span(1) for m in TITLED.finditer(text)]
    out = []
    for m in CAPS.finditer(text):                     # a run of capitalised words, none of them ordinary or organisational
        words, at = [], m.start()
        for word in m.group().split():
            start = text.index(word, at)
            at = start + len(word)
            if word.lower().strip("'’") in ORG_WORDS:
                if len(words) >= 2:
                    out.append((words[0][0], words[-1][1]))
                words = []
            else:
                words.append((start, at))
        if len(words) >= 2:
            out.append((words[0][0], words[-1][1]))
    return sorted(set(person)), sorted(set(out))


def main():
    nlp = spacy.load("en_core_web_sm")
    found = [spans(d) for d in nlp.pipe(json.load(sys.stdin))]
    json.dump({"person": [f[0] for f in found], "caps": [f[1] for f in found]}, sys.stdout)


if __name__ == "__main__":
    main()
