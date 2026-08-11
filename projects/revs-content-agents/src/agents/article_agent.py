from pathlib import Path

import pypandoc

from src.parsing.schemas import DesignBrief


class ArticleAgent:
    format_name = "articles"

    def _to_markdown(self, brief: DesignBrief) -> str:
        parts = [f"# {brief.headline}", "", brief.intro]
        for section in brief.sections:
            parts += ["", f"## {section.title}", "", section.body]
        if brief.closing_title:
            parts += ["", f"## {brief.closing_title}", "", brief.closing_body or ""]
        return "\n".join(parts) + "\n"

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
