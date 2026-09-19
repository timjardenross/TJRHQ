"""Mission 2 (Capacity & Attention Engine) §11/§26 — Cross-Surface
Consistency. attention_state.py's AttentionItem is consumed across a
Python/TypeScript boundary (this module's dicts become JSON served at
GET /brief/number-one, read by lcars-portal/src/lib/commandState.ts's
NumberOneAttentionItem-typed merge into buildNeedsYouItems()). There is no
compiler across that boundary -- a field renamed or retyped on either side
fails silently at runtime, not at build time.

This test proves the CONTRACT (field names, that a category value speaks
the same vocabulary) is currently held, by comparing AttentionItem.
to_dict()'s actual keys against a literal transcription of commandState.
ts's NumberOneAttentionItem interface as of this Mission 2 pass. It cannot
execute the TypeScript side, so it is not a substitute for the existing
per-language test suites (core/coordination/test_attention_state.py /
test_attention_state_capacity.py on the Python side, lcars-portal/src/lib/
__tests__/commandState.test.ts on the TS side) -- it exists specifically
to catch drift BETWEEN them that neither language's own suite can see.

KNOWN GAP as of this commit (Mission 2, not fixed here -- see this file's
own final test, which documents rather than silently ignores it):
commandState.ts's NumberOneAttentionItem does NOT yet declare
`capacity_adjusted_reason`, which attention_state.py's AttentionItem added
in this same Mission 2 pass. Until the Chair/Hub stream adds that field to
the TS interface (and decides how/whether to surface it in Needs You),
Python's capacity_adjusted_reason value is present in the JSON payload but
invisible to TypeScript's type system -- not a runtime break (TS ignores
unknown JSON fields), but a real, tracked drift this test will keep
failing on until reconciled, by design.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from attention_state import AttentionCategory, AttentionItem

# Literal transcription of lcars-portal/src/lib/commandState.ts's
# NumberOneAttentionCategory union, as of this Mission 2 pass.
TS_NUMBER_ONE_ATTENTION_CATEGORY = {
    "needs_now", "important_not_immediate", "can_wait", "blocked", "decision_required",
}

# Literal transcription of commandState.ts's NumberOneAttentionItem
# interface fields, as of this Mission 2 pass (does NOT yet include
# capacity_adjusted_reason -- see module docstring).
TS_NUMBER_ONE_ATTENTION_ITEM_FIELDS = {
    "id", "category", "priority", "title", "reason", "source", "ref", "generated_at",
}


def _sample_item() -> AttentionItem:
    return AttentionItem(
        id="number_one:priority:MSN-0001",
        category=AttentionCategory.NEEDS_NOW,
        priority=0,
        title="Sample",
        reason="Sample reason",
        source="number_one",
        ref="MSN-0001",
        generated_at="2026-09-19T00:00:00",
    )


class TestCategoryVocabularyMatchesTypeScript:
    def test_every_python_category_value_is_a_recognised_ts_literal(self):
        python_values = {c.value for c in AttentionCategory}
        assert python_values == TS_NUMBER_ONE_ATTENTION_CATEGORY, (
            "AttentionCategory drifted from commandState.ts's "
            "NumberOneAttentionCategory union -- update one side to match "
            "the other, and update this test's TS_NUMBER_ONE_ATTENTION_"
            "CATEGORY transcription."
        )


class TestFieldNamesMatchTypeScriptInterface:
    def test_serialized_fields_present_in_the_ts_interface_are_a_superset_or_exact_match(self):
        item = _sample_item()
        python_fields = set(item.to_dict().keys())
        # Every field the TS interface expects must exist in the Python
        # payload (a missing field IS a runtime break -- TS code reading
        # item.category on `undefined` fails loudly enough in practice,
        # but the point of this test is to catch it before that happens).
        missing_from_python = TS_NUMBER_ONE_ATTENTION_ITEM_FIELDS - python_fields
        assert not missing_from_python, (
            f"commandState.ts expects fields Python no longer serializes: {missing_from_python}"
        )

    def test_known_gap_capacity_adjusted_reason_not_yet_in_ts_interface(self):
        """Documents, rather than silently permits, the one known field
        drift as of this Mission 2 pass. This test is EXPECTED to start
        failing (in a good way) once the Chair/Hub stream adds
        capacity_adjusted_reason to commandState.ts's NumberOneAttentionItem
        -- at that point, update TS_NUMBER_ONE_ATTENTION_ITEM_FIELDS above
        to include it and delete this test, since the gap will be closed."""
        item = _sample_item()
        python_fields = set(item.to_dict().keys())
        extra_in_python = python_fields - TS_NUMBER_ONE_ATTENTION_ITEM_FIELDS
        assert extra_in_python == {"capacity_adjusted_reason"}, (
            "Expected exactly one known, tracked drift (capacity_adjusted_reason "
            f"present in Python, absent from the TS interface); found: {extra_in_python}. "
            "If this is now empty, the gap has been closed -- update the module "
            "docstring and TS_NUMBER_ONE_ATTENTION_ITEM_FIELDS, and delete this test."
        )
