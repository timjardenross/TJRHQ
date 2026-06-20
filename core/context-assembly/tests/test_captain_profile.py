"""
Validation: Captain Profile Knowledge Base is loaded correctly.
Run: python3 -m pytest tests/test_captain_profile.py -v
  or: python3 tests/test_captain_profile.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from loaders import load_captain_profile, load_corpus


def test_profile_file_exists():
    assert config.CAPTAIN_PROFILE_PATH.exists(), (
        f"Captain profile not found at {config.CAPTAIN_PROFILE_PATH}"
    )


def test_profile_loads():
    profile = load_captain_profile()
    assert profile, "load_captain_profile() returned empty dict"
    assert profile.get("text"), "profile has no text content"


def test_profile_metadata():
    profile = load_captain_profile()
    assert profile.get("source") == "captain_profile_knowledge_base", \
        f"Unexpected source: {profile.get('source')}"
    assert profile.get("version") == "1.0", \
        f"Unexpected version: {profile.get('version')}"
    assert profile.get("classification") == "Captain & XO Use", \
        f"Unexpected classification: {profile.get('classification')}"


def test_profile_key_sections():
    profile = load_captain_profile()
    text = profile.get("text", "")
    for section in ["IDENTITY", "CORE OBJECTIVES", "HEALTH PROFILE",
                    "COMMUNICATION PREFERENCES", "STARSHIP ENDEAVOUR VISION"]:
        assert section in text, f"Missing section in profile: {section}"


def test_profile_in_corpus():
    corpus = load_corpus()
    assert "captain_profile" in corpus, "captain_profile key missing from corpus"
    profile = corpus["captain_profile"]
    assert profile.get("text"), "captain_profile in corpus has no text"


def test_existing_corpus_keys_intact():
    corpus = load_corpus()
    for key in ("missions", "decisions", "adrs", "capabilities"):
        assert key in corpus, f"Corpus key missing after profile integration: {key}"


if __name__ == "__main__":
    tests = [
        test_profile_file_exists,
        test_profile_loads,
        test_profile_metadata,
        test_profile_key_sections,
        test_profile_in_corpus,
        test_existing_corpus_keys_intact,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed")
    sys.exit(0 if passed == len(tests) else 1)
