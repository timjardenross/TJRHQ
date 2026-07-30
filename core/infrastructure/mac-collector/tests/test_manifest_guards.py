from manifest_guards import (
    DEFAULT_EXCLUDE_EXTENSIONS,
    DEFAULT_INCLUDE_EXTENSIONS,
    ExtensionFilter,
    check_hard_stops,
)


def _entry(rel_path, size_bytes=100):
    return {"rel_path": rel_path, "size_bytes": size_bytes}


# -- ExtensionFilter -------------------------------------------------------

def test_default_include_extensions_pass():
    f = ExtensionFilter()
    for ext in DEFAULT_INCLUDE_EXTENSIONS:
        assert f.decide(f"Reference/doc{ext}").included


def test_default_exclude_extensions_blocked_by_default():
    f = ExtensionFilter()
    for ext in DEFAULT_EXCLUDE_EXTENSIONS:
        decision = f.decide(f"Photos/img{ext}")
        assert not decision.included
        assert ext in decision.reason


def test_unlisted_extension_blocked_by_default():
    f = ExtensionFilter()
    assert not f.decide("Notes/file.rtf").included


def test_extensionless_file_blocked():
    f = ExtensionFilter()
    assert not f.decide("Notes/README").included


def test_allow_ext_permits_normally_blocked_extension():
    f = ExtensionFilter(allow=["jpg", ".mp4"])
    assert f.decide("Photos/img.jpg").included
    assert f.decide("Videos/clip.mp4").included
    assert not f.decide("Photos/img.png").included


def test_extension_matching_case_insensitive():
    f = ExtensionFilter()
    assert f.decide("Reference/DOC.PDF").included


# -- check_hard_stops: max-files / max-total-bytes -------------------------

def test_max_files_hard_stop_triggers_over_limit():
    files = [_entry(f"Reference/doc{i}.pdf") for i in range(5)]
    result = check_hard_stops(files, max_files=4)
    assert result.stopped
    assert any("exceeding --max-files 4" in v for v in result.violations)


def test_max_files_hard_stop_not_triggered_at_or_under_limit():
    files = [_entry(f"Reference/doc{i}.pdf") for i in range(4)]
    result = check_hard_stops(files, max_files=4)
    assert not result.stopped


def test_max_total_bytes_hard_stop_triggers_over_limit():
    files = [_entry("Reference/big.pdf", size_bytes=2_000_000_000)]
    result = check_hard_stops(files, max_total_bytes=1_000_000_000)
    assert result.stopped
    assert any("exceeding --max-total-bytes" in v for v in result.violations)


def test_max_total_bytes_hard_stop_not_triggered_at_or_under_limit():
    files = [_entry("Reference/doc.pdf", size_bytes=500)]
    result = check_hard_stops(files, max_total_bytes=500)
    assert not result.stopped


def test_no_limits_configured_never_stops_on_count_or_size():
    files = [_entry(f"Reference/doc{i}.pdf", size_bytes=10**9) for i in range(1000)]
    result = check_hard_stops(files)
    assert not result.stopped


# -- check_hard_stops: Scoliosis Images ------------------------------------

def test_scoliosis_images_hard_stop_by_default():
    files = [_entry("Medical Reports/Scoliosis Images/scan1.pdf")]
    result = check_hard_stops(files)
    assert result.stopped
    assert any("Scoliosis Images" in v for v in result.violations)


def test_scoliosis_images_allowed_with_explicit_flag():
    files = [_entry("Medical Reports/Scoliosis Images/scan1.pdf")]
    result = check_hard_stops(files, allow_scoliosis_images=True)
    assert not result.stopped


def test_scoliosis_images_not_flagged_when_absent():
    files = [_entry("Medical Reports/report.pdf")]
    result = check_hard_stops(files)
    assert not result.stopped


# -- check_hard_stops: blocked extensions as a defensive re-check ----------

def test_blocked_extension_present_in_final_list_is_a_hard_stop():
    # Simulates the extension whitelist having been bypassed somehow
    # (e.g. --allow-ext used) — the hard-stop check still flags it so the
    # dry-run report is unambiguous about what's about to be transferred.
    files = [_entry("Photos/img.jpg")]
    result = check_hard_stops(files)
    assert result.stopped
    assert any("image/video/ebook" in v for v in result.violations)


# -- check_hard_stops: multiple simultaneous violations --------------------

def test_multiple_violations_all_reported():
    files = [
        _entry("Medical Reports/Scoliosis Images/scan1.pdf"),
        _entry("Photos/img.jpg"),
        _entry("Reference/doc.pdf"),
    ]
    result = check_hard_stops(files, max_files=2)
    assert result.stopped
    assert len(result.violations) == 3
