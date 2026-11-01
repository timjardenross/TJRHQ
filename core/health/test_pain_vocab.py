"""Pain readers: label new pain_state data, label old numeric as history,
and never turn a missing value into 0 / "no pain"."""
import pytest

from core.health.pain_vocab import PAIN_STATE_LABELS, describe_pain, pain_state_label


@pytest.mark.parametrize("state,label", [
    ("low", "Lower than usual"), ("baseline", "Around usual"),
    ("elevated", "Higher than usual"), ("high", "Much higher than usual"),
])
def test_state_labels(state, label):
    assert pain_state_label(state) == label
    assert describe_pain(state) == f"Pain vs usual: {label}"


def test_unknown_or_missing_state_is_none_not_a_default():
    assert pain_state_label(None) is None
    assert pain_state_label("") is None
    assert pain_state_label("severe") is None


def test_old_numeric_only_is_labelled_history():
    assert describe_pain(None, 6) == "Pain (older 0-10 record): 6/10"
    assert describe_pain(None, 6.5) == "Pain (older 0-10 record): 6.5/10"


def test_zero_is_a_real_old_value_and_is_kept_as_history():
    assert describe_pain(None, 0) == "Pain (older 0-10 record): 0/10"


def test_state_wins_and_number_is_appended_as_history():
    assert describe_pain("elevated", 7) == "Pain vs usual: Higher than usual (older 0-10 record: 7/10)"


def test_nothing_recorded_is_none_never_zero_or_no_pain():
    assert describe_pain(None, None) is None
    assert describe_pain("", None) is None


def test_label_set_matches_approved_wording():
    assert list(PAIN_STATE_LABELS.values()) == [
        "Lower than usual", "Around usual", "Higher than usual", "Much higher than usual",
    ]
