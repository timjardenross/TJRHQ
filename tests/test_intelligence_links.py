"""The Python-produced Intelligence link shape must match the portal route and its single TS builder (lcars-portal/src/lib/intelligenceLinks.ts)."""
import re
from pathlib import Path

from intelligence import tiered_brief as tb

ROOT = Path(__file__).resolve().parent.parent
TS = (ROOT / "lcars-portal/src/lib/intelligenceLinks.ts").read_text()
WB = ROOT / "lcars-portal/src/app/intelligence-workbench"


def _ts_const(name):
    return re.search(rf"export const {name} = '([^']+)'", TS).group(1)


def test_python_constants_equal_the_portal_builder():
    assert tb.INTELLIGENCE_HOME_PATH == _ts_const("INTELLIGENCE_HOME_PATH")
    assert tb.INCIDENTS_TAB == _ts_const("INCIDENTS_TAB")
    assert tb.PRODUCTS_TAB == _ts_const("PRODUCTS_TAB")
    assert "`${INTELLIGENCE_HOME_PATH}?tab=${tab}${anchor ? `#${anchor}` : ''}`" in TS  # same ?tab=<tab>#<anchor> shape


def test_link_resolves_to_a_real_route_and_tab():
    link = tb.incident_link("inc-0123456789", base="https://hq.example.test/")
    assert link == "https://hq.example.test/intelligence-workbench?tab=incidents#inc-0123456789"
    assert (WB / "page.tsx").is_file()  # the route exists
    page = (WB / "page.tsx").read_text()
    for tab in (tb.INCIDENTS_TAB, tb.PRODUCTS_TAB):
        assert f"{{ key: '{tab}'," in page and f"tab === '{tab}'" in page  # tab is registered and rendered


def test_retired_page_is_a_pointer_without_panels():
    stub = (ROOT / "lcars-portal/src/app/(app)/intelligence/page.tsx").read_text()
    assert "IncidentsView" not in stub and "IntelligenceProducts" not in stub and "IncidentsPanel" not in stub
