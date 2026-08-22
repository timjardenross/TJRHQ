from pathlib import Path

from PyPDF2 import PdfReader

from src.agents.worksheet_agent import WorksheetAgent, _extract_checklist_items


def test_extracts_exactly_the_12_systems_not_the_later_example_list(brief):
    """Regression test: this section also contains a later 'Example:' bullet
    list (Pain: 6/10, Nervous System: 3/10, ...) that must NOT be swept in -
    a prior version of this extraction grabbed 16 items instead of 12."""
    items = _extract_checklist_items(brief)
    assert len(items) == 12
    assert items[0] == "Pain & Physical Load"
    assert items[-1] == "Purpose & Meaning"
    assert not any("6/10" in item or "3/10" in item for item in items)


def test_generate_creates_pdf_with_one_field_per_item(brief, tmp_path):
    result = WorksheetAgent().generate(brief, tmp_path)
    assert result["format"] == "worksheets"

    pdf_path = Path(result["files"][0])
    assert pdf_path.exists()
    fields = PdfReader(str(pdf_path)).get_fields()
    assert len(fields) == 12
