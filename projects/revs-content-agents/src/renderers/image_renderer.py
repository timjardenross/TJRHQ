import textwrap

from PIL import ImageDraw, ImageFont
from PIL.Image import Image

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_FONT_PATH, size)
    except OSError:
        return ImageFont.load_default()


def add_headline_banner(image: Image, headline: str, primary_color: str, banner_ratio: float = 0.22) -> Image:
    """Draw a solid-color banner with wrapped headline text across the top of `image`."""
    image = image.convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    banner_height = int(height * banner_ratio)
    draw.rectangle([0, 0, width, banner_height], fill=primary_color)

    font_size = max(14, int(banner_height * 0.16))
    font = _load_font(font_size)
    padding = int(width * 0.05)
    max_text_width = width - 2 * padding

    char_width = font.getlength("M") or (font_size * 0.6)
    wrap_width = max(10, int(max_text_width / char_width))
    lines = textwrap.wrap(headline.upper(), width=wrap_width, max_lines=3, placeholder="...")

    line_height = int(font_size * 1.35)
    total_text_height = line_height * len(lines)
    y = max(padding // 2, (banner_height - total_text_height) // 2)
    for line in lines:
        draw.text((padding, y), line, font=font, fill="white")
        y += line_height

    return image
