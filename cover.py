"""Create a KDP Kindle eBook cover from an existing chapter illustration."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

COVER_SIZE = (1600, 2560)
FONT_CANDIDATES = (
    '/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc',
    '/System/Library/Fonts/AppleSDGothicNeo.ttc',
    '/System/Library/Fonts/Hiragino Sans GB.ttc',
    '/Library/Fonts/Arial Unicode.ttf',
    'C:/Windows/Fonts/meiryo.ttc',
    'C:/Windows/Fonts/YuGothM.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    raise RuntimeError('A Japanese TrueType font is required to render the cover.')


def draw_centered(draw: ImageDraw.ImageDraw, text: str, y: int,
                  font: ImageFont.FreeTypeFont, fill: str) -> None:
    bounds = draw.textbbox((0, 0), text, font=font, stroke_width=1)
    width = bounds[2] - bounds[0]
    draw.text(((COVER_SIZE[0] - width) / 2, y), text, font=font, fill=fill,
              stroke_width=1, stroke_fill='#07121f')


def create_kdp_cover(illustration_path: Path, title: str, author: str,
                     output_path: Path) -> Path:
    """Render a 1600x2560 RGB JPEG cover without changing source artwork."""
    with Image.open(illustration_path) as source:
        illustration = ImageOps.exif_transpose(source).convert('RGB')

    background = ImageOps.fit(illustration, COVER_SIZE, method=Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(48))
    background = ImageEnhance.Brightness(background).enhance(0.28)
    canvas = background.convert('RGBA')
    tint = Image.new('RGBA', COVER_SIZE, (5, 17, 32, 115))
    canvas = Image.alpha_composite(canvas, tint)

    glow = Image.new('RGBA', COVER_SIZE, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((170, 770, 1430, 1950), fill=(31, 144, 196, 70))
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(120)))

    draw = ImageDraw.Draw(canvas)
    draw_centered(draw, 'がでがる', 145, load_font(174), '#f8fbff')
    draw_centered(draw, 'ZERO', 355, load_font(166), '#f0a762')
    draw_centered(draw, '〜最初の一滴〜', 575, load_font(88), '#d8f2ff')
    draw_centered(draw, '第一話・第二話収録', 758, load_font(42), '#b7cbdc')

    panel = ImageOps.contain(illustration, (1460, 850), method=Image.Resampling.LANCZOS)
    panel_x = (COVER_SIZE[0] - panel.width) // 2
    panel_y = 950
    panel_mask = Image.new('L', panel.size, 0)
    ImageDraw.Draw(panel_mask).rounded_rectangle(
        (0, 0, panel.width - 1, panel.height - 1), radius=28, fill=255)
    draw.rounded_rectangle((panel_x - 6, panel_y - 6,
                            panel_x + panel.width + 5, panel_y + panel.height + 5),
                           radius=34, outline='#c3efff', width=4)
    canvas.paste(panel, (panel_x, panel_y), panel_mask)

    draw = ImageDraw.Draw(canvas)
    draw_centered(draw, '空を覆う巨大円盤。', 1870, load_font(56), '#f8fbff')
    draw_centered(draw, '三人の出会いが、物語を始める。', 1960,
                  load_font(48), '#d5e7f5')
    draw_centered(draw, author, 2180, load_font(66), '#f0a762')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert('RGB').save(output_path, 'JPEG', quality=92, optimize=True,
                               progressive=True, dpi=(72, 72))
    return output_path