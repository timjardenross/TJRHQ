import textwrap

from PIL import ImageDraw, ImageFont
from PIL.Image import Image

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def add_headline_banner(
    image: Image, headline: str, primary_color: str,
    banner_ratio: float = 0.22, max_banner_ratio: float = 0.4,
) -> Image:
    """Draw a solid-color banner with the wrapped headline across the top of `image`.

    Grows the banner (and shrinks the font, down to a floor) to fit the full
    headline instead of truncating it with "..." - a long concept title should
    still be fully readable, not cut off mid-word."""
    image = image.convert("RGB")
    width, height = image.size
    padding = int(width * 0.05)
    max_text_width = width - 2 * padding
    text = headline.upper()

    font_size = max(14, int(height * banner_ratio * 0.16))
    min_font_size = max(12, int(font_size * 0.55))

    while True:
        font = _load_font(font_size)
        char_width = font.getlength("M") or (font_size * 0.6)
        wrap_width = max(10, int(max_text_width / char_width))
        lines = textwrap.wrap(text, width=wrap_width)
        line_height = int(font_size * 1.35)
        banner_height = max(int(height * banner_ratio), line_height * len(lines) + padding)
        if banner_height <= height * max_banner_ratio or font_size <= min_font_size:
            break
        font_size -= 2

    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, banner_height], fill=primary_color)
    y = max(padding // 2, (banner_height - line_height * len(lines)) // 2)
    for line in lines:
        draw.text((padding, y), line, font=font, fill="white")
        y += line_height

    return image
