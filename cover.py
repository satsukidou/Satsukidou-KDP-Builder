"""Create a KDP Kindle eBook cover from an existing chapter illustration."""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from urllib.parse import unquote

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

COVER_SIZE = (1600, 2560)
KDP_MAX_COVER_BYTES = 50 * 1024 * 1024
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


def select_cover_candidates(chapters: list[dict], image_root: Path,
                            count: int = 3, use_web_images: bool = True) -> list[dict]:
    if not use_web_images or count <= 0:
        return []

    candidates = []
    for chapter in chapters:
        for image in chapter.get('images', []):
            relative_path = image.get('path')
            if not relative_path:
                continue
            image_path = image_root / relative_path
            try:
                with Image.open(image_path) as source:
                    width, height = source.size
            except (OSError, ValueError):
                width, height = 0, 0

            source_name = unquote(image.get('source_url', ''))
            context = image.get('context', '')
            searchable = ' '.join((source_name, image.get('alt', ''), context))
            score = 0
            reasons = []
            keyword_groups = (
                (('三人', '3人', '三人組'), 5, '三人のチーム要素'),
                (('宇宙船', '母艦', 'UFO', 'ufo', '円盤'), 4, '巨大宇宙船'),
                (('青白', '光輪', '光', '照射'), 2, '青白い光'),
                (('オフィス', 'office', 'コーヒー', '珈琲', 'デスク'), 3, '第一話の日常'),
            )
            for keywords, points, reason in keyword_groups:
                if any(keyword in searchable for keyword in keywords):
                    score += points
                    reasons.append(reason)

            if width and height:
                portrait_ratio = height / width
                if height > width:
                    score += max(0, 3 - round(abs(portrait_ratio - 1.6) * 3))
                    reasons.append('縦長構図')
            candidates.append({
                'chapter_title': chapter.get('title', ''),
                'image_path': relative_path,
                'source_url': image.get('source_url', ''),
                'alt': image.get('alt', ''),
                'context': context,
                'width': width,
                'height': height,
                'score': score,
                'reasons': reasons,
            })

    candidates.sort(key=lambda item: (-item['score'], item['image_path']))
    return candidates[:count]


def build_cover_metadata(book_config: dict, chapters: list[dict],
                         candidates: list[dict]) -> dict:
    cover = book_config.get('cover', {})
    full_title = book_config.get('title', '')
    title = cover.get('title') or full_title.split('〜', 1)[0].strip()
    subtitle = cover.get('subtitle')
    if subtitle is None and '〜' in full_title:
        subtitle = full_title.split('〜', 2)[1].strip()
    return {
        'title': title,
        'subtitle': subtitle or '',
        'author': book_config.get('author', ''),
        'episodes': [{'title': chapter.get('title', ''), 'url': chapter.get('url', '')}
                     for chapter in chapters],
        'summary': cover.get('summary', ''),
        'characters': cover.get('characters', []),
        'motifs': cover.get('motifs', []),
        'concept': cover.get('concept', 'episode1_and_2_combined'),
        'cover_specs': {
            'format': cover.get('format', 'jpg'),
            'width': cover.get('width', 1600),
            'height': cover.get('height', 2560),
            'include_title_text': cover.get('include_title_text', True),
        },
        'candidates': candidates,
    }


def build_cover_prompt(metadata: dict, candidate: dict, variant: int) -> str:
    scenes = (
        'オフィスの窓辺、コーヒーカップのある日常の向こうに巨大円盤が現れ、青白い光が差し込む瞬間',
        '紗月・ルナ・ティルスの三人が手を取り合い、巨大宇宙船へ青白い光に包まれて浮かび上がる瞬間',
        '巨大宇宙船の光輪と内部構造を背景に、三人が新しい冒険へ踏み出す物語の始まり',
    )
    scene = scenes[(variant - 1) % len(scenes)]
    specs = metadata['cover_specs']
    text_layout = (
        f'表紙に「{metadata["title"]}」「{metadata["subtitle"]}」'
        f'「{metadata["author"]}」を正確に表示し、上部に読みやすく配置する。'
        if specs['include_title_text'] else
        '文字は描かず、上部と下部にタイトル・著者名を後から置ける余白を確保する。'
    )
    character_text = '、'.join(metadata['characters'])
    motif_text = '、'.join(metadata['motifs'])
    context = candidate.get('context', '')
    reference = f'参考画像: {candidate["image_path"]}。' if candidate.get('image_path') else ''
    return '\n'.join([
        '日本語ライトノベルのKDP電子書籍表紙イラスト。',
        f'タイトル: {metadata["title"]}。副題: {metadata["subtitle"]}。著者: {metadata["author"]}。',
        f'収録話: {"、".join(episode["title"] for episode in metadata["episodes"])}。',
        f'物語の要約: {metadata["summary"]}',
        f'登場人物: {character_text}。主要モチーフ: {motif_text}。',
        f'象徴的な情景: {scene}。',
        f'参考画像の周辺本文: {context}',
        reference,
        text_layout,
        f'縦長比率 {specs["width"]}:{specs["height"]}。イラストを上下左右の端まで全面に描き、枠や余白を作らない。',
        '小さなサムネイルでも主役と題名が判別できる構図。',
        '壮大で神秘的、日常から非日常へ切り替わる高揚感。高品質なライトノベル表紙、余計な文字や透かしなし。',
    ])


def generate_cover_package(book_config: dict, chapters: list[dict],
                           image_root: Path, cover_dir: Path) -> dict:
    cover = book_config.get('cover', {})
    draft_count = max(1, int(cover.get('draft_count', 3)))
    use_web_images = cover.get('use_web_images', True)
    candidates = select_cover_candidates(
        chapters,image_root,draft_count,use_web_images=use_web_images)
    metadata = build_cover_metadata(book_config,chapters,candidates)
    specs = metadata['cover_specs']
    if specs['format'].lower().lstrip('.') not in ('jpg','jpeg'):
        raise ValueError('Cover format must be JPG or JPEG.')
    if specs['width'] <= 0 or specs['height'] <= 0:
        raise ValueError('Cover width and height must be positive integers.')

    cover_dir.mkdir(parents=True,exist_ok=True)
    (cover_dir/'cover_metadata.json').write_text(
        json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    prompt_paths=[]
    for index in range(1,draft_count+1):
        candidate=candidates[index-1] if index <= len(candidates) else {}
        prompt=build_cover_prompt(metadata,candidate,index)
        prompt_path=cover_dir/f'cover_prompt_{index:02d}.txt'
        prompt_path.write_text(prompt+'\n',encoding='utf-8')
        prompt_paths.append(prompt_path)
    (cover_dir/'cover_prompt.txt').write_text(
        prompt_paths[0].read_text(encoding='utf-8'),encoding='utf-8')

    draft_paths=[]
    if use_web_images:
        composed_title=metadata['title']
        if metadata['subtitle']:
            composed_title+=f' 〜{metadata["subtitle"]}〜'
        for index,candidate in enumerate(candidates,1):
            draft_path=cover_dir/f'cover_draft_{index:02d}.jpg'
            create_kdp_cover(image_root/candidate['image_path'],composed_title,
                             metadata['author'],draft_path,width=specs['width'],
                             height=specs['height'],
                             include_title_text=specs['include_title_text'])
            draft_paths.append(draft_path)

    selected_cover=cover.get('selected_cover')
    if selected_cover:
        selected_name=Path(selected_cover).name
        selected_path=cover_dir/selected_name
        if selected_name != selected_cover or not selected_path.is_file():
            raise FileNotFoundError(f'Selected cover not found in cover directory: {selected_cover}')
        final_name=cover.get('output_final_name','cover_final.jpg')
        if Path(final_name).name != final_name or Path(final_name).suffix.lower() not in ('.jpg','.jpeg'):
            raise ValueError('output_final_name must be a JPG filename.')
        shutil.copyfile(selected_path,cover_dir/final_name)
    return {'metadata':metadata,'prompts':prompt_paths,'drafts':draft_paths}


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
                     output_path: Path, width: int = 1600, height: int = 2560,
                     include_title_text: bool = True) -> Path:
    """Render a configurable RGB JPEG cover without changing source artwork."""
    with Image.open(illustration_path) as source:
        illustration = ImageOps.exif_transpose(source).convert('RGB')

    canvas = ImageOps.fit(illustration, COVER_SIZE, method=Image.Resampling.LANCZOS,
                          centering=(0.5, 0.5)).convert('RGBA')
    overlay = Image.new('RGBA', COVER_SIZE, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for y in range(COVER_SIZE[1]):
        top_alpha = max(0, 190 * (1 - y / 1050))
        bottom_alpha = max(0, 190 * ((y - 1550) / (COVER_SIZE[1] - 1550)))
        alpha = int(max(top_alpha, bottom_alpha))
        if alpha:
            overlay_draw.line((0, y, COVER_SIZE[0], y), fill=(4, 14, 28, alpha))
    canvas = Image.alpha_composite(canvas, overlay)

    if include_title_text:
        draw = ImageDraw.Draw(canvas)
        main_title, separator, subtitle = title.partition('〜')
        subtitle = subtitle.partition('〜')[0] if separator else ''
        series = main_title.replace('ZERO','').strip()
        draw_centered(draw, series or main_title, 145, load_font(174), '#f8fbff')
        if 'ZERO' in main_title:
            draw_centered(draw, 'ZERO', 355, load_font(166), '#f0a762')
        if subtitle:
            draw_centered(draw, f'〜{subtitle}〜', 575, load_font(88), '#d8f2ff')
        draw_centered(draw, '第一話・第二話収録', 758, load_font(42), '#b7cbdc')

    if include_title_text:
        draw = ImageDraw.Draw(canvas)
        draw_centered(draw, '空を覆う巨大円盤。', 1870, load_font(56), '#f8fbff')
        draw_centered(draw, '三人の出会いが、物語を始める。', 1960,
                      load_font(48), '#d5e7f5')
        draw_centered(draw, author, 2180, load_font(66), '#f0a762')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output=canvas.convert('RGB')
    if (width,height) != COVER_SIZE:
        output=output.resize((width,height),Image.Resampling.LANCZOS)
    output.save(output_path, 'JPEG', quality=92, optimize=True,
                progressive=True, dpi=(72, 72))
    return output_path


def prepare_user_cover(source_path: Path, output_path: Path, preview_path: Path,
                       width: int = 1600, height: int = 2560,
                       fit_mode: str = 'contain', max_bytes: int = KDP_MAX_COVER_BYTES,
                       preview_width: int = 800) -> dict:
    if width <= 0 or height <= 0 or preview_width <= 0:
        raise ValueError('Cover dimensions must be positive integers.')
    if fit_mode not in ('contain', 'cover'):
        raise ValueError('fit_mode must be contain or cover.')
    size_limit = min(max_bytes, KDP_MAX_COVER_BYTES)
    if size_limit <= 0:
        raise ValueError('max_bytes must be positive.')

    with Image.open(source_path) as source:
        original = ImageOps.exif_transpose(source).convert('RGBA')
        source_size = original.size

    target_size = (width, height)
    background = ImageOps.fit(original.convert('RGB'), target_size,
                              method=Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(max(12, min(target_size) // 35)))
    background = ImageEnhance.Brightness(background).enhance(0.35)
    canvas = background.convert('RGBA')

    if fit_mode == 'contain':
        artwork = original.copy()
        artwork.thumbnail(target_size, Image.Resampling.LANCZOS)
        position = ((width - artwork.width) // 2, (height - artwork.height) // 2)
    else:
        artwork = ImageOps.fit(original, target_size, method=Image.Resampling.LANCZOS,
                               centering=(0.5, 0.5))
        position = (0, 0)
    content_size = artwork.size
    canvas.alpha_composite(artwork, position)

    final_image = canvas.convert('RGB')
    encoded = None
    quality = 92
    while quality >= 56:
        buffer = io.BytesIO()
        final_image.save(buffer, 'JPEG', quality=quality, optimize=True,
                         progressive=True, dpi=(72, 72))
        encoded = buffer.getvalue()
        if len(encoded) <= size_limit:
            break
        quality -= 6
    if encoded is None or len(encoded) > size_limit:
        raise ValueError('Cover image cannot be compressed below the configured size limit.')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encoded)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview = final_image.copy()
    preview_height = max(1, round(preview_width * height / width))
    preview.thumbnail((preview_width, preview_height), Image.Resampling.LANCZOS)
    preview.save(preview_path, 'JPEG', quality=88, optimize=True)
    return {
        'source_size': source_size,
        'content_size': content_size,
        'width': width,
        'height': height,
        'format': 'JPEG',
        'mode': 'RGB',
        'fit_mode': fit_mode,
        'bytes': len(encoded),
        'preview_width': preview.width,
        'preview_height': preview.height,
    }