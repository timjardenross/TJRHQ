from src.parsing.schemas import DesignBrief

# Feeding a section's raw body (headers, colons, numbered lists) as "context"
# reliably makes Gemini typeset it as a mock poster/infographic - including a
# hallucinated headline and a placeholder credit line like "Graphic by [Your
# Organization/Name]" - even though the prompt says "no readable text". The
# brief's intro is guaranteed prose (see brief_parser.py), not a structured
# list, so it primes the model toward abstract art instead of a document to
# render. The no-text instruction is also repeated at the end, since models
# weight the tail of a prompt more heavily.
_NO_TEXT = (
    "CRITICAL: pure abstract artwork only - absolutely no text, words, letters, "
    "numbers, titles, captions, labels, or credit lines anywhere in the image, "
    "not even small or stylized. Shapes and color only, nothing typeset."
)


def hero_art_prompt(brief: DesignBrief, subject: str) -> str:
    theme = brief.intro[:300]
    return (
        f"A calming, editorial illustration for {subject} about: '{brief.headline}'. "
        f"Thematic context: {theme} "
        "Style: soft abstract interlocking shapes suggesting connected systems, muted "
        "therapeutic color palette, no visible faces, hopeful and grounded mood, clear "
        "open negative space across the top third for a headline overlay. "
        f"{_NO_TEXT}"
    )
