#!/usr/bin/env python3
"""Synthetic validation of the privacy screening, before any historical record. Fictional people only.
Run on the host under `unshare -n`. Passes only when every planted name, contact, birth detail and adverse or sensitive case is flagged,
clean controls pass, and a detector failure holds the record. Prints identifiers of cases and classes only."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import screen

# (kind, title, summary, allowed dispositions, personal names planted). Titles are ordinary length so that nothing is held by accident.
H, R, E = ("held",), ("held", "review"), ("eligible",)
CASES = [
    ("clean", "Prudential regulator releases new operational risk standard", "The standard applies to insurers from next year.", E, ()),
    ("clean", "Consultation on liquidity reporting for banks", "Submissions close in March.", E, ()),
    ("clean", "Quarterly statistics for superannuation funds published", "Total assets rose over the quarter.", E, ()),
    ("clean", "Minutes of the monetary policy meeting released", "The board considered labour market conditions.", E, ()),
    ("clean", "Guidance on managing service provider arrangements updated", "Entities should review material arrangements.", E, ()),
    ("clean", "APRA consults on changes to the Banking Prudential Standard", "The Reserve Bank of Australia was consulted.", E, ()),
    ("official_in_role", "Speech by Chair Jonathan Fairweather to the banking forum", "Chair Jonathan Fairweather discussed resilience.", ("eligible", "review"), ("Jonathan Fairweather",)),
    ("official_in_role", "Remarks from Deputy Governor Priya Raman on payments", "Deputy Governor Priya Raman spoke about payments.", ("eligible", "review"), ("Priya Raman",)),
    ("official_in_role", "Treasurer announces a new board appointment", "The Treasurer announced that Member Daniel Okafor was appointed.", ("eligible", "review"), ("Daniel Okafor",)),
    ("private_individual", "A letter was received about an account", "Margaret Ellison wrote about her account.", R, ("Margaret Ellison",)),
    ("private_individual", "A short story from the local community", "Tomasz Kowalczyk runs a small bakery in town.", R, ("Tomasz Kowalczyk",)),
    ("private_individual", "An invitation to the neighbourhood this weekend", "Please welcome Nguyen Thi Lan to the neighbourhood.", R, ("Nguyen Thi Lan",)),
    ("private_individual", "Some feedback was received from the public", "We heard from Aroha Ngata last week.", R, ("Aroha Ngata",)),
    ("private_individual", "A matter was raised at the counter yesterday", "Mr Okonkwo raised the matter at the counter.", R, ("Okonkwo",)),
    ("private_individual", "A question was asked at the public session", "Siobhan O'Callaghan-Byrne asked a question.", R, ("Siobhan",)),
    ("private_individual", "Reporting update from the public enquiry line", "Wei Zhang and Fatima Al-Rashid sent a complaint.", R, ("Wei Zhang", "Fatima")),
    ("adverse", "Regulator disqualifies a company officer from acting", "Michael Thornbury was disqualified from acting as a director.", H, ("Michael Thornbury",)),
    ("adverse", "A court action has begun this week", "Rebecca Stanton was charged with fraud offences.", H, ("Rebecca Stanton",)),
    ("adverse", "An enforcement outcome has been recorded today", "APRA accepted an enforceable undertaking from Harold Penrose.", H, ("Harold Penrose",)),
    ("adverse", "Regulator opens an inquiry into senior conduct", "The regulator is investigating Chief Executive Alan Whitby for breaches of duty.", H, ("Alan Whitby",)),
    ("adverse", "A penalty has been imposed by the court", "The former director was fined by the court.", H, ()),
    ("adverse", "A departure was announced by the firm", "A manager was sacked after misconduct.", H, ()),
    ("health", "A statement about a leadership change today", "Susan Marlowe was diagnosed with cancer and has stepped down.", H, ("Susan Marlowe",)),
    ("health", "An update about a senior office holder", "The treasurer is in hospital after a heart attack.", H, ()),
    ("sensitive", "A profile of a recent complaint to the office", "Omar Haddad, a Muslim community member, lodged a complaint.", H, ("Omar Haddad",)),
    ("sensitive", "A profile of a recent claim to the office", "Ellen Brightwater says her disability affected her claim.", H, ("Ellen Brightwater",)),
    ("child", "An incident was reported to the office today", "A 9-year-old boy was named in the report.", H, ()),
    ("contact", "Consultation on reporting changes is now open", "Send comments to jane.citizen@example.com by Friday.", H, ()),
    ("contact", "Enquiries about the new reporting standard", "Call the officer on 0412 345 678.", H, ()),
    ("contact", "Enquiries about the new reporting standard", "Phone (02) 9123 4567 for details.", H, ()),
    ("contact", "Enquiries about the new reporting standard", "Phone +61 3 9876 5432.", H, ()),
    ("birth", "An application record was filed this week", "Date of birth 3 May 1970 is recorded.", H, ()),
    ("birth", "An application record was filed this week", "The applicant was born on 12/07/1968.", H, ()),
    ("birth", "An application record was filed this week", "Born in 1975, the applicant lives locally.", H, ()),
    ("birth", "An application record was filed this week", "The applicant, aged 47, applied again.", H, ()),
    ("address", "A public meeting notice for next week", "The meeting was held at 14 Wattle Street.", H, ()),
    ("identifier", "A record quoted in a recent submission", "Tax file number 123 456 789 was quoted.", H, ()),
]


def main():
    screen.must_be_offline()
    sys.path.insert(0, screen.APP)
    from core.security import public_judgement_route as route

    results, failed, missed_names = [], [], []
    detector = screen.union_detector(route)
    for n, (kind, title, summary, allowed, names) in enumerate(CASES, 1):
        text = f"{title}. {summary}"
        spans = detector(text)
        for name in names:
            at = text.index(name)
            if not any(start < at + len(name) and end > at for start, end in spans):
                missed_names.append(f"syn-{n:02d}")
        event = {"event_id": f"syn-{n:02d}", "source_id": screen.COHORT[0], "raw_title": title, "raw_summary": summary,
                 "canonical_url": "https://www.apra.gov.au/synthetic"}
        disposition, rules = screen.screen_events([event], {screen.COHORT[0]: "APRA"}, route, detector)[event["event_id"]]
        results.append((event["event_id"], kind, disposition, rules))
        if disposition not in allowed or any("screening_failed" in r for r in rules):
            failed.append(event["event_id"])

    def broken(_text):
        raise RuntimeError("detector unavailable")

    event = {"event_id": "syn-failure", "source_id": screen.COHORT[0], "raw_title": CASES[0][1], "raw_summary": "", "canonical_url": "https://www.apra.gov.au/x"}
    disposition, rules = screen.screen_events([event], {screen.COHORT[0]: "APRA"}, route, broken)["syn-failure"]
    if disposition != "held":
        failed.append("syn-failure")
    addresses = {"https://www.apra.gov.au/a": True, "https://apra.gov.au/a": True, "https://apra.gov.au.example.com/a": False, "https://notapra.gov.au/a": False,
                 "https://apra.gov.au@example.com/a": False, "https://user@www.apra.gov.au/a": False, "http://www.apra.gov.au/a": False,
                 "https://www.rba.gov.au/a": False, "https://[bad": False, "https://www.apra.gov.au:99999/a": False, "": False, None: False,
                 "https://news.google.com/rss/articles/x": False}
    bad_addresses = [str(u) for u, want in addresses.items() if screen.address_established({"canonical_url": u}, "APRA") is not want]
    for case, kind, disposition, rules in results:
        print(f"{case} {kind:18} {disposition:8} {' '.join(rules)}")
    print(json.dumps({"cases": len(CASES), "failed": failed, "names_missed": missed_names, "detector_failure_disposition": "held" if "syn-failure" not in failed else "NOT HELD",
                      "address_cases": len(addresses), "address_failures": len(bad_addresses), "network": "none (unshare)", **screen.versions()}))
    return 1 if failed or missed_names or bad_addresses else 0


if __name__ == "__main__":
    sys.exit(main())
