import re
from pathlib import Path

from src.integrations.gemini_client import generate_speech
from src.parsing.schemas import DesignBrief

_MARKDOWN_STRIP_RE = re.compile(r"[*_#]")


def _build_script(brief: DesignBrief) -> str:
    parts = [brief.headline, brief.intro]
    for section in brief.sections:
        parts += [section.title, section.body]
    if brief.closing_title:
        parts += [brief.closing_title, brief.closing_body or ""]
    script = "\n\n".join(p for p in parts if p)
    return _MARKDOWN_STRIP_RE.sub("", script)


class PodcastAgent:
    format_name = "podcasts"

    def generate(self, brief: DesignBrief, output_dir: Path) -> dict:
        out_dir = output_dir / self.format_name
        out_dir.mkdir(parents=True, exist_ok=True)

        script = _build_script(brief)
        transcript_path = out_dir / f"{brief.concept_id}_transcript.txt"
        transcript_path.write_text(script, encoding="utf-8")

        audio_path = out_dir / f"{brief.concept_id}.wav"
        generate_speech(script, out_path=str(audio_path))

        return {"format": self.format_name, "files": [str(transcript_path), str(audio_path)]}
