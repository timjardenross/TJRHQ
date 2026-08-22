import re
from pathlib import Path

import pypandoc

from src.integrations.gemini_client import generate_text
from src.parsing.schemas import DesignBrief
from src.utils.logging import get_logger

log = get_logger("article_agent")

_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s")
_UNDER_TARGET_RATIO = 0.9  # only expand if meaningfully short, not just a few words off

_EXPAND_PROMPT = """The following is a section of an article, currently {actual} words. \
Expand it to approximately {target} words by adding relevant depth, detail, examples, \
or elaboration on the points already present.

- Do not remove, change, or contradict any existing fact or claim.
- Do not add filler, repetition, or generic padding - every added sentence must carry \
real content.
- Preserve the existing Markdown structure (bullet points, bold text, sub-headers) \
exactly where already present.
- Match the existing tone and voice.
- Output only the expanded section text, nothing else - no preamble, no note about \
what you changed.

Section:
{body}"""


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


def _expand_if_short(title: str, body: str, word_target: int | None) -> str:
    if not word_target:
        return body
    actual = len(body.split())
    if actual >= word_target * _UNDER_TARGET_RATIO:
        return body
    log.info(f"expanding section {title!r}: {actual}w -> ~{word_target}w target")
    return generate_text(_EXPAND_PROMPT.format(actual=actual, target=word_target, body=body)).strip()


class ArticleAgent:
    format_name = "articles"

    def _to_markdown(self, brief: DesignBrief) -> str:
        parts = [f"# {brief.headline}", "", brief.intro]
        for section in brief.sections:
            body = _expand_if_short(section.title, section.body, section.word_target)
            parts += ["", f"## {section.title}", "", body]
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
