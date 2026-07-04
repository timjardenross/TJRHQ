from path_filters import PathFilter, path_matches


# -- path_matches --------------------------------------------------------

def test_path_matches_folder_prefix():
    assert path_matches("Operational Resilience/foo.pdf", "Operational Resilience/")
    assert path_matches("Operational Resilience/sub/bar.docx", "Operational Resilience")
    assert not path_matches("Operational Resilience 2/foo.pdf", "Operational Resilience/")


def test_path_matches_bare_component_anywhere():
    assert path_matches("Starship Intake/Transfer 1/old.pdf", "Transfer 1")
    assert not path_matches("Starship Intake/Transfer 10/old.pdf", "Transfer 1")


def test_path_matches_glob_extension():
    assert path_matches("Medical Reports/scan1.jpg", "*.jpg")
    assert path_matches("Medical Reports/clip.mp4", "*.mp4")
    assert not path_matches("Medical Reports/report.pdf", "*.jpg")


# -- PathFilter ------------------------------------------------------------

def test_no_filters_includes_everything():
    f = PathFilter()
    assert f.decide("Operational Resilience/foo.pdf").included
    assert f.decide("Scoliosis Images/scan.jpg").included


def test_include_only_named_folders():
    f = PathFilter(include=["Operational Resilience/", "PECB/", "Medical Reports/"])
    assert f.decide("Operational Resilience/foo.pdf").included
    assert f.decide("PECB/cert.pdf").included
    assert f.decide("Medical Reports/report.pdf").included
    assert not f.decide("Scoliosis Images/scan.jpg").included
    assert not f.decide("Transfer 1/old.pdf").included
    assert not f.decide("A_Cleanup/misc.pdf").included


def test_exclude_wins_over_include():
    f = PathFilter(
        include=["Medical Reports/"],
        exclude=["Medical Reports/Scoliosis Images/"],
    )
    assert f.decide("Medical Reports/report.pdf").included
    assert not f.decide("Medical Reports/Scoliosis Images/scan.jpg").included


def test_exclude_only_no_include_restriction():
    f = PathFilter(exclude=["Scoliosis Images/", "*.mp4", "*.jpg"])
    assert f.decide("Operational Resilience/foo.pdf").included
    assert not f.decide("Scoliosis Images/scan.jpg").included
    assert not f.decide("Operational Resilience/clip.mp4").included
