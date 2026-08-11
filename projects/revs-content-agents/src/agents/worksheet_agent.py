import re
from pathlib import Path

from weasyprint import HTML
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

from src.parsing.schemas import DesignBrief

_PAGE_WIDTH, _PAGE_HEIGHT = 612, 792  # US Letter, points
_MARGIN = 54  # 0.75in
_HEADER_HEIGHT = 140
_ITEM_HEIGHT = 34
_FIELD_WIDTH = 200
_FIELD_HEIGHT = 18

_BULLET_RE = re.compile(r"^-\s+(.+)$")


def _first_bullet_run(body: str) -> list[str]:
    """A section body can contain more than one bullet list (e.g. the real
    checklist plus a later worked example). Only the first contiguous run of
    '- ' lines is the checklist; later ones are illustrative, not fields."""
    items: list[str] = []
    started = False
    for line in body.splitlines():
        match = _BULLET_RE.match(line)
        if match:
            started = True
            items.append(match.group(1).strip("* "))
        elif started:
            break
    return items


def _extract_checklist_items(brief: DesignBrief) -> list[str]:
    """Find the bullet list this brief uses for self-assessment (e.g. a rate-1-10
    system list). Prefers a section about applying/using the framework; falls back
    to the first section with a bullet list, then to section titles."""
    ranked = sorted(
        brief.sections,
        key=lambda s: 0 if re.search(r"use|framework|steps|apply", s.title, re.I) else 1,
    )
    for section in ranked:
        items = _first_bullet_run(section.body)
        if items:
            return items[:20]
    return [s.title for s in brief.sections] or [brief.headline]


class WorksheetAgent:
    format_name = "worksheets"

    def _build_html(self, brief: DesignBrief, items: list[str]) -> str:
        rows = "\n".join(f'<div class="item"><span class="label">{item}</span></div>' for item in items)
        return f"""
        <html><head><style>
            @page {{ size: {_PAGE_WIDTH}pt {_PAGE_HEIGHT}pt; margin: {_MARGIN}pt; }}
            body {{ font-family: sans-serif; color: #1a1a1a; }}
            h1 {{ font-size: 20pt; margin-bottom: 4pt; }}
            .subtitle {{ font-size: 12pt; color: #555; margin-bottom: 6pt; }}
            .instructions {{ font-size: 10pt; color: #333; margin-bottom: 18pt; }}
            .item {{ height: {_ITEM_HEIGHT}pt; display: flex; align-items: center;
                      border-bottom: 1px solid #ccc; }}
            .label {{ font-size: 11pt; width: 340px; }}
        </style></head><body>
            <h1>{brief.headline}</h1>
            <div class="subtitle">Self-Assessment Worksheet</div>
            <div class="instructions">
                Rate each item below from 1 (depleted) to 10 (full capacity).
                Fill in the box next to each line.
            </div>
            {rows}
        </body></html>
        """

    def _add_text_fields(self, pdf_path: Path, items: list[str]) -> None:
        reader = PdfReader(str(pdf_path))
        writer = PdfWriter()
        writer.append_pages_from_reader(reader)
        page = writer.pages[0]

        field_refs = ArrayObject()
        for i, _ in enumerate(items):
            top_y = _HEADER_HEIGHT + i * _ITEM_HEIGHT + (_ITEM_HEIGHT - _FIELD_HEIGHT) / 2
            y2 = _PAGE_HEIGHT - _MARGIN - top_y
            y1 = y2 - _FIELD_HEIGHT
            x1 = _MARGIN + 340
            x2 = x1 + _FIELD_WIDTH

            field = DictionaryObject({
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/T"): TextStringObject(f"rating_{i + 1}"),
                NameObject("/Rect"): RectangleObject((x1, y1, x2, y2)),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/F"): NumberObject(4),  # Print flag
                NameObject("/DA"): TextStringObject("/Helv 10 Tf 0 g"),
                NameObject("/V"): TextStringObject(""),
            })
            field_ref = writer._add_object(field)
            page[NameObject("/Annots")] = page.get("/Annots", ArrayObject())
            page["/Annots"].append(field_ref)
            field_refs.append(field_ref)

        acroform = DictionaryObject({
            NameObject("/Fields"): field_refs,
            NameObject("/NeedAppearances"): BooleanObject(True),
        })
        writer._root_object[NameObject("/AcroForm")] = acroform

        with open(pdf_path, "wb") as f:
            writer.write(f)

    def generate(self, brief: DesignBrief, output_dir: Path) -> dict:
        out_dir = output_dir / self.format_name
        out_dir.mkdir(parents=True, exist_ok=True)

        items = _extract_checklist_items(brief)
        html = self._build_html(brief, items)

        pdf_path = out_dir / f"{brief.concept_id}.pdf"
        HTML(string=html).write_pdf(str(pdf_path))

        self._add_text_fields(pdf_path, items)

        return {"format": self.format_name, "files": [str(pdf_path)]}
