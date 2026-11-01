import re
from pathlib import Path

from src.integrations.gemini_client import generate_speech, generate_text
from src.parsing.schemas import DesignBrief

_MARKDOWN_STRIP_RE = re.compile(r"[*_#]")

_NARRATION_PROMPT = """Rewrite the following content so it reads naturally as spoken \
podcast narration, without changing its meaning, tone, or leaving anything out.

- Remove all Markdown formatting (no **, ###, bullet dashes, numbered list markers).
- Expand ratio notation into words (e.g. "5/10" becomes "five out of ten").
- Replace the "↔" symbol with a natural spoken connector like "and" or "affects".
- Turn bullet/numbered lists into flowing spoken sentences, not a concatenation of \
fragments with no connective language.
- Keep every fact, number, and idea from the original - this must be a full, faithful \
narration script, not a summary or abridgement.
- Do not add any new commentary, introduction, or sign-off beyond what the content \
already implies.
- Output only the rewritten narration text, nothing else.

Content to adapt:
{script}"""


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

        raw_script = _build_script(brief)
        narration = generate_text(_NARRATION_PROMPT.format(script=raw_script)).strip()

        transcript_path = out_dir / f"{brief.concept_id}_transcript.txt"
        transcript_path.write_text(narration, encoding="utf-8")

        audio_path = out_dir / f"{brief.concept_id}.wav"
        generate_speech(narration, out_path=str(audio_path))

        return {"format": self.format_name, "files": [str(transcript_path), str(audio_path)]}
