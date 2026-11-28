#!/usr/bin/env python3
"""Local export and privacy screening of the pilot cohort. Run as root on the host; record content never leaves it.

  screen.py export DIR         one repeatable-read snapshot of the cohort through the approved read views (root only: DIR is 0700)
  screen.py run DIR            classify every record; writes DIR/holds.json and DIR/screening.csv (identifiers and classes only)

Reuses the programme's local screening (identifier, address, health and conduct wording, and the on-host person detector). Run `run`
under `unshare -n`: it needs no network and refuses to start if it has one. Nothing printed contains record content.
"""
# ruff: noqa: SIM115  (small single-user command-line tool)
import asyncio
import csv
import hashlib
import json
import os
import random
import re
import socket
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import package_c

APP = "/opt/starship-endeavour"
COHORT = ("3b4edf0b-cbf9-4859-9fc0-a315276b7437", "c715aa9e-dbf2-4af9-9445-339a14bc3bd4", "e86ae4aa-7c94-41b7-80fb-e1b644fed8cf",
          "b92f589e-5ddf-4328-a984-fd2bdb33bf99", "2c99282c-0f57-4384-950d-f9a71a916f0a")
WATERMARK = "2026-11-28 04:21:33+00"
CONTACT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|(?<![\w-])(?:\+?61|0)[2-478](?:[ -]?\d){8}(?![\w-])")


async def export(folder):
    sys.path.insert(0, "/root/prodops-assurance")
    import assurance_query

    ids = ",".join(f"'{i}'" for i in COHORT)
    con = await assurance_query.connect()
    try:
        async with con.transaction(isolation="repeatable_read", readonly=True):
            events = [dict(r) for r in await con.fetch(f"select {', '.join(package_c.EVENT_FIELDS)} from assurance.events "
                                                       f"where source_id::text in ({ids}) and collected_at <= timestamptz '{WATERMARK}'")]
            edges = [dict(r) for r in await con.fetch("select cohort_event_id, relation, linked_id from assurance.package_c_links where relation <> 'record'")]
            names = await con.fetch(f"select source_id, source_name from assurance.sources where source_id::text in ({ids})")
            as_of = await con.fetchval("select now()")
    finally:
        await con.close()
    sources = []
    for n in names:
        licence = package_c.LICENCE["RBA" if "RBA" in n["source_name"] else "APRA"]
        sources.append({"source_id": str(n["source_id"]), "source_name": n["source_name"], "licence_url": licence[0], "attribution": licence[1]})
    os.umask(0o077)
    manifest = package_c.write_export(folder, events, edges, sources, as_of=as_of.isoformat(), synthetic=False)
    os.chmod(folder, 0o700)
    print(json.dumps({"as_of": manifest["as_of"], "counts": manifest["counts"], "digests": manifest["digests"]}))


RULES_VERSION = "C1-E2"
ROLE = (r"(?:Deputy |Assistant )?(?:Chair(?:man|woman|person)?|Governor|Treasurer|Member|Minister|President|Secretary|Commissioner)"
        r"|(?:APRA|RBA) Member|(?:Executive |General |Managing )?Director|Chief (?:Executive|Risk|Operating|Economist|Financial)(?: Officer)?|CEO|Head of [A-Z][A-Za-z]+")
IN_ROLE = re.compile(r"\b(?:speech|remarks|address|statement|opening|keynote|testimony|interview|appearance|letter) (?:by|from|of|to|with|before)\b|\b(?:appear\w+|chair(?:s|ed)|present\w+|respond\w+|writes?|wrote|joins?|joined|retir\w+|step\w+ down|conclud\w+)\b|'s (?:speech|remarks|address|statement|opening|testimony)\b|\b(?:said|says|announc\w+|speak\w*|spoke|deliver\w+|appoint\w+|address\w*|welcom\w+|"
                     r"decid\w+|commenced|discuss\w+|told|noted|outlined)\b", re.IGNORECASE)
# wording the earlier supervised screening does not list but that is adverse or sensitive when it is about a person
ADVERSE = re.compile(r"\b(?:disqualif\w+|enforceable undertaking|civil penalt\w+|prosecut\w+|investigat\w+|breach(?:es|ed)? (?:of )?(?:duty|duties|the act)|charges? against|facing charges|"
                     r"fraud\w*|bankrupt\w+|insolven\w+|court|proceedings|fined|penalt\w+|removed from|infringement|dismiss\w+|resign\w+ (?:amid|after|following))\b", re.IGNORECASE)
OFFICE_HOLDER = re.compile(r"\b(?:the|a|an|former|its|his|her) (?:\w+ )?(?:treasurer|chair(?:man|woman|person)?|governor|secretary|commissioner|president|minister|applicant|executive)\b", re.IGNORECASE)
# attributes the earlier screening does not list, and wording that marks someone as a private individual
SENSITIVE_MORE = re.compile(r"\b(?:church|mosque|synagogue|congregation|parish)(?:\w*)? (?:member|goer|volunteer|elder)|\b(?:union (?:member|delegate|official|representative)|trade unionist|"
                            r"member of (?:a|the) (?:\w+ )?(?:union|church|party)|party member|political affiliation|on (?:sick|medical|mental health|parental|compassionate) leave)\b", re.IGNORECASE)
PRIVATE = re.compile(r"\b(?:pensioner|retiree|customer|consumer|complainant|resident|policy ?holder|borrower|depositor|tenant|widow|widower)\b", re.IGNORECASE)
BIRTH = re.compile(r"\b(?:born (?:on |in )?\d|born in [A-Z]|aged \d{1,3}\b|\d{1,3}[- ]year[- ]old|date of birth|d\.o\.b)", re.IGNORECASE)
PHONE = re.compile(r"(?<![\w-])(?:\+?61[ -]?\(?0?\)?|\(0[2-478]\)|0)[ -]?[2-478]?(?:[ -]?\d){8}(?!\d)|\b1[38]00(?:[ -]?\d){6}\b")
RIGHTS = re.compile(r"\b(?:coat of arms|logo|reproduced with permission|copyright of|third[- ]party material|photograph|banknotes?|cash rate (?:data|series|statistics)|financial data|econometric model)\b", re.IGNORECASE)
FURNITURE = re.compile(r"^(?:home|search|news|media|publications|consultations|speeches|contact us|about(?: us)?|subscribe|read more|menu|skip to .*|page \d+)$", re.IGNORECASE)


def address_established(event, publisher):
    """E-2: an absolute https address whose parsed host is the publisher's domain or below it (dot boundary). Never fetched or repaired."""
    try:
        url = urllib.parse.urlsplit(str(event.get("canonical_url") or ""))
        host = (url.hostname or "").rstrip(".").lower()
        url.port  # noqa: B018 - raises on a malformed port
    except ValueError:
        return False
    domain = {"APRA": "apra.gov.au", "RBA": "rba.gov.au"}[publisher]
    return url.scheme == "https" and not url.username and not url.password and (host == domain or host.endswith("." + domain))


def person_key(span_text):
    return " ".join(w.lower() for w in name_words(span_text))


def officeholders(texts, detector):
    """The locally kept list of office holders: names the cohort itself gives with an official role. Never printed or shared."""
    names = set()
    for text in texts:
        for start, end in detector(text):
            key = person_key(text[start:end])
            if not key or len(key.split()) < 2:
                continue
            name = re.escape(" ".join(name_words(text[start:end])))
            if re.search(rf"\b(?:{ROLE})\b,? (?:(?:Mr|Ms|Mrs|Dr|Professor) )?{name}|{name},? (?:the |APRA's |RBA's |its |new )?(?:{ROLE})\b|{name},? (?:has been |was |is )?appointed", text):
                names.add(key)
    return frozenset(names)


def named_in_role(text, spans, officers=frozenset()):
    """Every detected name sits with an official role in its sentence, and the sentence shows the person acting in it."""
    for start, end in spans:
        left = max(text.rfind(c, 0, start) for c in ".!?;") + 1
        stops = [i for i in (text.find(c, end) for c in ".!?;") if i >= 0]
        sentence, name = text[left:min(stops, default=len(text))], text[start:end]
        name = re.sub(rf"^(?:(?:APRA|RBA|Mr|Ms|Mrs|Dr|Professor)\.? |(?:{ROLE})\b,? )+", "", name)     # a detector span may include the title
        beside = rf"(?:\b(?:{ROLE})\b,? (?:(?:Mr|Ms|Mrs|Dr|Professor) )?{re.escape(name)}|{re.escape(name)}, (?:the |APRA's |RBA's |its |new )?(?:{ROLE})\b)"
        appointed = rf"{re.escape(name)},? (?:has been |was |is |will be )?appointed (?:as )?(?:the |an? )?(?:new )?(?:{ROLE})\b"
        official = person_key(name) in officers or re.search(beside, sentence) or re.search(appointed, sentence)
        if not (official and IN_ROLE.search(sentence)):
            return False
    return True


ROLE_WORDS = {"apra", "rba", "mr", "ms", "mrs", "dr", "professor", "chair", "chairman", "chairwoman", "deputy", "assistant", "governor", "treasurer",
              "member", "minister", "president", "secretary", "commissioner", "director", "executive", "general", "managing", "chief", "head"}
TITLE_BEFORE = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Professor|Prof|Sir|Dame|Hon)\.? *$")


def load_vocabulary(path=None):
    """Words seen in lower case in collected public reporting: ordinary words, which a personal name is not. Absent file: nothing is ordinary."""
    path = path or os.environ.get("INTEL_VOCABULARY", "")
    if not path or not os.path.exists(path):
        return frozenset()
    with open(path, encoding="utf-8") as fh:
        return frozenset(line.strip().lower() for line in fh if line.strip())


def name_words(span_text):
    return [w for w in re.findall(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", span_text) if w.lower().rstrip("'’s") not in ROLE_WORDS and w.lower() not in ROLE_WORDS]


def could_be_name(text, start, end, vocabulary):
    """False only when every word of the span is an ordinary word (or a role word) and no personal title introduces it."""
    if TITLE_BEFORE.search(text[:start]) or TITLE_BEFORE.match(text[start:end].split(" ")[0] + " "):
        return True
    words = name_words(text[start:end])
    return any(re.sub(r"['’]s$", "", w.lower()) not in vocabulary for w in words)


def union_detector(route, batch=25, vocabulary=None):
    """The existing on-host person detector plus the over-inclusive second finder; a failure of either raises, so the record is held.
    ``prime(texts)`` runs both over many texts with few model loads; a text not primed is detected on its own."""
    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "names_worker.py")
    cache: dict[str, list] = {}
    ordinary = load_vocabulary() if vocabulary is None else vocabulary

    def second(texts):
        r = subprocess.run([f"{APP}/platform-runtime/.venv-llmsec/bin/python", "-B", worker], input=json.dumps(texts), capture_output=True,
                           text=True, check=True, timeout=300)
        out = json.loads(r.stdout)
        if len(out) != len(texts):
            raise ValueError("name finder returned the wrong number of results")
        return out

    def merge(spans):
        merged = []
        for start, end in sorted(set(spans)):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        return merged

    def run_batch(texts):
        bounds, at = [], 0
        for t in texts:
            bounds.append((at, at + len(t)))
            at += len(t) + 3
        joined = route.person_spans("\n.\n".join(texts))
        for t, (lo, hi), extra in zip(texts, bounds, second(texts), strict=True):
            found = merge([(s - lo, min(e, hi) - lo) for s, e in joined if lo <= s < hi] + [tuple(x) for x in extra])
            cache[t] = [(s, e) for s, e in found if could_be_name(t, s, e, ordinary)]

    def detect(text):
        if text not in cache:
            run_batch([text])
        return cache[text]

    def prime(texts):
        todo = [t for t in dict.fromkeys(texts) if t not in cache]
        for i in range(0, len(todo), batch):
            try:
                run_batch(todo[i:i + batch])
            except Exception:  # noqa: BLE001, S112 - left unprimed: each record is then tried alone and held if it still fails
                continue

    detect.prime = prime
    return detect


def text_of(event):
    return f"{str(event.get('raw_title') or '').strip()}. {str(event.get('raw_summary') or '').strip()}".strip()


def classify(event, publisher, route, detector, officers=frozenset()):
    """(disposition, [rule:class, ...]). Every rule that matched is listed; anything not eligible is not copied."""
    held, review = [], []
    if event.get("source_id") not in COHORT:
        held.append("E-1:out_of_scope")
    if not address_established(event, publisher):
        held.append("E-2:source_or_address_not_established")
    title = str(event.get("raw_title") or "").strip()
    if not title or FURNITURE.match(title):
        held.append("E-3:not_an_item")
    elif len(title.split()) < 3:
        review.append("E-3:item_unclear")
    text = text_of(event)
    if RIGHTS.search(text):
        review.append("E-4:rights_unclear")
    spans = detector(text)
    if route.sensitive({"r": text}, lambda _joined: spans).get("r"):
        held.append("E-5:identifier_or_sensitive")
    if CONTACT.search(text) or PHONE.search(text):
        held.append("E-5:direct_contact")
    if BIRTH.search(text):
        held.append("E-5:birth_detail")
    adverse = bool(route._CONDUCT.search(text) or route._CHILD_OR_VICTIM.search(text) or route._HEALTH.search(text) or ADVERSE.search(text))
    person = bool(spans) or bool(route._INDIVIDUAL.search(text) or route._PERSON_WORD.search(text) or OFFICE_HOLDER.search(text))
    if person and adverse:
        held.append("E-5:adverse_or_sensitive_about_individual")
    elif adverse:
        review.append("E-5:adverse_wording_no_person_found")
    if spans and SENSITIVE_MORE.search(text):
        held.append("E-5:sensitive_attribute_about_individual")
    if spans and PRIVATE.search(text):
        held.append("E-5:private_individual")
    elif spans and not named_in_role(text, spans, officers):
        review.append("E-5:person_role_unclear")
    flagged = ["E-5:official_named_in_role"] if spans and not held and not review else []
    if held:
        return "held", held + review
    return ("review", review) if review else ("eligible", flagged)


def versions():
    code = os.path.abspath(__file__)
    out = {"rules": RULES_VERSION, "screen_py_sha256": hashlib.sha256(open(code, "rb").read()).hexdigest()[:16]}
    venv = f"{APP}/platform-runtime/.venv-llmsec/bin/python"
    out["names_worker_sha256"] = hashlib.sha256(open(os.path.join(os.path.dirname(code), "names_worker.py"), "rb").read()).hexdigest()[:16]
    probe = "import importlib.metadata as m; print(';'.join(f'{p}={m.version(p)}' for p in ('presidio-analyzer','spacy','en-core-web-sm')))"
    r = subprocess.run([venv, "-c", probe], capture_output=True, text=True, check=False)
    out["detector"] = r.stdout.strip() or "unknown"
    return out


def must_be_offline():
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=2).close()
    except OSError:
        return
    raise SystemExit("refused: run under unshare -n; this step must have no network")


def screen_events(events, publishers, route, detector):
    out = {}
    if hasattr(detector, "prime"):
        detector.prime([text_of(e) for e in events])
    try:
        officers = officeholders([text_of(e) for e in events], detector)
    except Exception:  # noqa: BLE001 - without the list, names without a role in their own sentence stay held for review
        officers = frozenset()
    for e in events:
        try:
            out[e["event_id"]] = classify(e, publishers.get(e["source_id"], "APRA"), route, detector, officers)
        except Exception as exc:  # noqa: BLE001 - unscreenable is held; the message may quote content, so only the type is kept
            out[e["event_id"]] = ("held", ["E-5:screening_failed_" + type(exc).__name__])
    return out


def run(folder, route=None, detector=None, require_offline=True):
    if require_offline:
        must_be_offline()
    if route is None:
        sys.path.insert(0, APP)
        from core.security import public_judgement_route as route
    detector = detector or union_detector(route, vocabulary=load_vocabulary(os.path.join(folder, "vocabulary.txt")))
    _manifest, data = package_c.load_export(folder)
    publishers = {s["source_id"]: "RBA" if "rba.gov.au" in s["licence_url"] else "APRA" for s in data["sources"]}
    results = screen_events(data["events"], publishers, route, detector)
    os.umask(0o077)
    json.dump({k: {"disposition": d, "rules": r} for k, (d, r) in results.items() if d != "eligible"}, open(f"{folder}/holds.json", "w"), indent=1)
    with open(f"{folder}/screening.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(("event_id", "source_id", "disposition", "rules"))
        source = {e["event_id"]: e["source_id"] for e in data["events"]}
        w.writerows(sorted((k, source[k], d, " ".join(r)) for k, (d, r) in results.items()))
    sheet(folder, data["events"], results)
    counts, rules = {}, {}
    for d, r in results.values():
        counts[d] = counts.get(d, 0) + 1
        for x in r:
            rules[x] = rules.get(x, 0) + 1
    return {"records": len(results), "dispositions": counts, "rule_counts": dict(sorted(rules.items())), **versions()}


def sheet(folder, events, results, sample=10):
    """For the principal only, on this host: records held for review, and a random sample of at least ten passed ones. Contains record text:
    root-only, never read by a hosted assistant."""
    passed = sorted(k for k, (d, _r) in results.items() if d == "eligible")
    picked = random.SystemRandom().sample(passed, min(sample, len(passed)))
    by_id = {e["event_id"]: e for e in events}
    with open(f"{folder}/REVIEW-SHEET.txt", "w", encoding="utf-8") as fh:
        for heading, ids in (("HELD FOR YOUR REVIEW", sorted(k for k, (d, _r) in results.items() if d == "review")), ("SPOT CHECK OF PASSED RECORDS", picked)):
            fh.write(f"== {heading} ({len(ids)})\n")
            for k in ids:
                e = by_id[k]
                fh.write(f"\n{k}  {' '.join(results[k][1])}\n  {e.get('raw_title')}\n  {e.get('raw_summary') or ''}\n  {e.get('canonical_url') or ''}\n")


if __name__ == "__main__":
    if sys.argv[1] == "export":
        asyncio.run(export(sys.argv[2]))
    else:
        print(json.dumps(run(sys.argv[2])))
