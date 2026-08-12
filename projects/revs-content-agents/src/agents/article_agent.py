import re
from pathlib import Path

import pypandoc

from src.parsing.schemas import DesignBrief

_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s")


def _ensure_blank_line_before_lists(text: str) -> str:
    """CommonMark only starts a list at a blank line, document start, or another
    list item - a '- item' line right after a paragraph/bold-header line with no
    blank line between them is a "lazy continuation" of that paragraph, not a new
    list. Briefs are commonly authored as "**Monday:**\\n- Pain: 5/10\\n..." with
    no blank line, which pandoc then renders as one run-on <p>, not a <ul>. Insert
    the missing blank line before each list's first item (not between items)."""
    lines = text.split("\n")
    result = []
    prev_was_list = False
    for line in lines:
        is_list = bool(_LIST_ITEM_RE.match(line))
        if is_list and not prev_was_list and result and result[-1].strip() != "":
            result.append("")
        result.append(line)
        prev_was_list = is_list
    return "\n".join(result)


class ArticleAgent:
    format_name = "articles"

    def _to_markdown(self, brief: DesignBrief) -> str:
        parts = [f"# {brief.headline}", "", brief.intro]
        for section in brief.sections:
            parts += ["", f"## {section.title}", "", section.body]
        if brief.closing_title:
            parts += ["", f"## {brief.closing_title}", "", brief.closing_body or ""]
        markdown = "\n".join(parts) + "\n"
        return _ensure_blank_line_before_lists(markdown)

    def generate(self, brief: DesignBrief, output_dir: Path) -> dict:
        out_dir = output_dir / self.format_name
        out_dir.mkdir(parents=True, exist_ok=True)

        markdown = self._to_markdown(brief)
        md_path = out_dir / f"{brief.concept_id}.md"
        md_path.write_text(markdown, encoding="utf-8")

        html_path = out_dir / f"{brief.concept_id}.html"
        pypandoc.convert_text(
            markdown, "html", format="md",
            outputfile=str(html_path),
            extra_args=["--standalone", f"--metadata=title:{brief.headline}"],
        )

        return {"format": self.format_name, "files": [str(md_path), str(html_path)]}
