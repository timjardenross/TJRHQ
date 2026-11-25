"""Health guard on safety signals MISCLASSIFIED as ordinary study results: detections, misses and false positives are all counted.

The misclassified set is synthetic notice-style wording plus real-shaped routine research titles (public-style, fictional drugs). Numbers are
asserted so that a change in the lexicon that silently loses recall or adds noise fails here. See the Batch 1 logic engineering report for the production
measurement (279 labelled safety rows, 777 curator-suppressed rows)."""
import importlib.util
import os

_P = os.path.join(os.path.dirname(__file__), "..", "tools", "health-osint", "curation_guard.py")
_spec = importlib.util.spec_from_file_location("curation_guard_fl", _P)
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)

MASK = {"signal_type": "study_result", "health_domain": "treatment", "fda_flagged": None, "adverse_event_text": None}

SAFETY_MISCLASSIFIED = [
    "Recall of Brandex 20 mg tablets after contamination found",
    "Agency warns about liver injury with Zorvanta",
    "Boxed warning added to Neurazol label",
    "Drug safety communication: stop using Vexil injection pens",
    "Three deaths reported after Colvera infusion",
    "Product withdrawn from the market over overdose risk",
    "Life-threatening allergic reaction reported with Pelmax",
    "Anaphylaxis cases prompt safety alert for Rinvoke-like agent",
    "Regulator urges patients to stop using Tarvex gel",
    "Fatal overdoses linked to counterfeit Oxalin tablets",
    "Hospitalisations rise after use of recalled eye drops",
    "Safety concerns raised over Dolmetrix dosing",
    # wording with no lexicon term: expected MISSES, counted below
    "Liver failure reported in patients taking Zorvanta, agency investigating",
    "Patients should check batch numbers of Calmora syrup",
    "Regulator investigating heart rhythm problems linked to Vexil",
    "New interaction may cause severe bleeding with Tarvex",
]
ROUTINE = [
    "Effectiveness of Healthy Habits for Older Adults: a randomised trial",
    "Reducing Blood Culture Contamination With a Diversion Device: PIVO Trial",
    "Resurgence of Chikungunya in Thailand: surveillance report",
    "Opioid-free anaesthesia compared with standard care in knee surgery",
    "A Study to Assess the Safety and Efficacy of Brandex in Adults With Asthma",
    "Weight Management Program for Obese Preschool Children",
    "Impact of dose <2 mg and >10 mg on sleep latency",
    "Exercise training for chronic back pain in adults",
    "Vitamin D supplementation and bone density: a meta-analysis",
    "Mediterranean diet and cognitive decline cohort study",
    "Ebola disease outbreak, regional situation update",
    "Phase II study of a vaccine candidate in healthy adults",
]


def _hit(text):
    sig = {**MASK, "title": text}
    return bool(g.deterministic_safety_indicators(sig) or g.source_text_lexicon_indicators(sig))


def test_misclassified_safety_detection_and_misses_are_counted():
    hits = [t for t in SAFETY_MISCLASSIFIED if _hit(t)]
    misses = [t for t in SAFETY_MISCLASSIFIED if not _hit(t)]
    assert len(hits) == 12 and len(misses) == 4         # recall 12/16 = 75% on this set; the 4 misses use no lexicon term
    assert all("Zorvanta" in m or "Calmora" in m or "Vexil" in m or "Tarvex" in m for m in misses)


def test_routine_titles_false_positives_are_counted():
    fps = [t for t in ROUTINE if _hit(t)]
    assert fps == ["Reducing Blood Culture Contamination With a Diversion Device: PIVO Trial"]   # 1/12; comparison signs untouched


def test_deterministic_fields_alone_still_escalate_when_present():
    assert g.deterministic_safety_indicators({**MASK, "fda_flagged": True})
    assert g.deterministic_safety_indicators({**MASK, "adverse_event_text": "rash"})
    assert not g.deterministic_safety_indicators({**MASK})       # masked type/domain and no flags: nothing deterministic remains
