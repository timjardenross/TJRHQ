"""Units that start their command through run-with-infisical*.sh are ordered
After=docker.service (USS-TJR-MSN-0407).

Infisical runs as a docker container, so the daemon has to be up before any
wrapper can log in. This only orders against the daemon; the container itself
may still be starting, which is what the wrapper's own readiness wait
(platform-runtime/lib-infisical.sh) covers. alert-on-failure@ is exempt: an
alert path must not be delayed behind docker.
"""

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"
EXEMPT = {"alert-on-failure@.service"}


def _wrapper_units():
    return sorted(
        p for p in DEPLOY.glob("*.service")
        if re.search(r"run-with-infisical(-bot)?\.sh", p.read_text(encoding="utf-8"))
        and p.name not in EXEMPT
    )


def _unit_section_after(text):
    unit = re.split(r"^\[(?!Unit\])", text, maxsplit=1, flags=re.MULTILINE)[0]
    return " ".join(m.group(1) for m in re.finditer(r"^After=(.*)$", unit, flags=re.MULTILINE)).split()


def test_there_are_wrapper_units_to_check():
    assert len(_wrapper_units()) >= 15


def test_every_wrapper_unit_is_ordered_after_docker():
    missing = [p.name for p in _wrapper_units() if "docker.service" not in _unit_section_after(p.read_text(encoding="utf-8"))]
    assert not missing, f"missing After=docker.service: {missing}"
