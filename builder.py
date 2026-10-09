#!/usr/bin/env python3
"""WordPress article -> source HTML, locally referenced images and Markdown.

The original article body is saved unchanged as source HTML. Markdown conversion
is an output representation, not a claim of byte-for-byte textual identity.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup, NavigableString, Tag
from cover import create_kdp_cover

USER_AGENT = 'Satsukidou-KDP-Builder/0.1 (+personal archival use)'
SELECTORS = ['.entry-content', '.post-content', '.single-content', 'article .content', 'article']


def select_article(soup):
    for css in SELECTORS:
        matches = soup.select(css)
        if matches:
            match = max(matches, key=lambda x: len(x.get_text(' ', strip=True)))
            if len(match.get_text(' ', strip=True)) > 20:
                return match
    raise ValueError('Article body not found; inspect site HTML and update SELECTORS.')


def clean_article(article):
    """Remove embedded sharing/widgets, not article paragraphs or figures."""
    for node in article.select('script, style, nav, .sharedaddy, .jp-relatedposts, .yarpp-related, .post-navigation, .advertisement'):
        node.decompose()
    return article


def image_url(img, page_url):
    # Prefer the image shown in the content, not a low-resolution lazy placeholder.
    candidate = (img.get('data-orig-file') or img.get('data-full-url') or
                 img.get('data-src') or img.get('src'))
    if not candidate:
        candidates = (img.get('data-srcset') or img.get('srcset') or '').split(',')
        if candidates:
            candidate = candidates[-1].strip().split(' ')[0]
    if not candidate or candidate.startswith('data:'):
        return None
    return urljoin(page_url, candidate)


def fetch(session, url, timeout=30):
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def flatten_blocks(node):
    """Walk the WordPress body in document order, avoiding duplicated nested text."""
    blocks = []
    def walk(parent):
        for child in parent.children:
            if not isinstance(child, Tag):
                continue
            name = child.name.lower()
            if name in ('h1','h2','h3','h4','h5','h6'):
                blocks.append(('heading', int(name[1]), child.get_text(' ', strip=True)))
            elif name == 'img':
                blocks.append(('image',child))
            elif name == 'figure':
                imgs = child.find_all('img')
                for img in imgs: blocks.append(('image', img))
                cap = child.find('figcaption')
                if cap: blocks.append(('paragraph', cap.get_text(' ',strip=True)))
            elif name in ('p','blockquote','pre'):
                # Include inline formatting where possible; preserve text content.
                if child.find('img'):
                    for img in child.find_all('img'): blocks.append(('image', img))
                t = child.get_text('\n' if name == 'pre' else '', strip=True)
                if t: blocks.append(('paragraph', t))
            elif name == 'li':
                blocks.append(('list',child.get_text(' ', strip=True)))
            elif name in ('hr',):
                blocks.append(('rule',))
            elif name in ('div','section','main','article','ul','ol','a'):
                walk(child)
            elif child.find(['p','img','figure','div','h2','h3']):
                walk(child)
    walk(node)
    return blocks


def safe_image_name(index, url, content):
    suffix = ''
    if content.startswith(b'\x89PNG\r\n\x1a\n'):
        suffix = '.png'
    elif content.startswith(b'\xff\xd8\xff'):
        suffix = '.jpg'
    elif content.startswith((b'GIF87a', b'GIF89a')):
        suffix = '.gif'
    elif content.startswith(b'RIFF') and content[8:12] == b'WEBP':
        suffix = '.webp'
    elif len(content) >= 12 and content[4:8] == b'ftyp' and content[8:12] in (b'avif', b'avis'):
        suffix = '.avif'
    elif content.startswith(b'BM'):
        suffix = '.bmp'
    elif content.startswith((b'II*\x00', b'MM\x00*')):
        suffix = '.tif'
    else:
        prefix = content.lstrip().lower()[:512]
        if b'<svg' in prefix:
            suffix = '.svg'
    if not suffix:
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix == '.jpeg':
            suffix = '.jpg'
        if suffix not in ('.jpg', '.png', '.gif', '.webp', '.avif', '.bmp', '.tif', '.tiff', '.svg'):
            suffix = '.img'
    return f'image_{index:03d}{suffix}'


def normalize_text(value):
    return re.sub(r'\s+', ' ', value).strip()


def source_events(html):
    soup = BeautifulSoup(html, 'html.parser')
    article = clean_article(select_article(soup))
    events = []
    image_ordinal = 0
    for block in flatten_blocks(article):
        kind = block[0]
        if kind == 'image':
            image_ordinal += 1
            events.append(('image', image_ordinal))
        elif kind == 'heading':
            events.append(('text', normalize_text(block[2])))
        elif kind in ('paragraph', 'list'):
            events.append(('text', normalize_text(block[1])))
        elif kind == 'rule':
            events.append(('rule', ''))
    return events


def markdown_events(markdown):
    events = []
    for block in markdown.split('\n\n'):
        block = block.strip()
        if not block or block.startswith('<!-- MISSING IMAGE:'):
            continue
        image = re.fullmatch(r'!\[([^]]*)\]\(([^)]+)\)', block)
        if image:
            events.append(('image', image.group(2)))
        elif block == '---':
            events.append(('rule', ''))
        else:
            text = re.sub(r'^#{1,6}\s+', '', block)
            text = re.sub(r'^[-*+]\s+', '', text)
            events.append(('text', normalize_text(text)))
    return events


def validate_chapter(html, markdown, out_dir, manifest):
    source = source_events(html)
    converted = markdown_events(markdown)
    source_text = [value for kind, value in source if kind == 'text']
    markdown_text = [value for kind, value in converted if kind == 'text']
    mismatches = []
    for index in range(max(len(source_text), len(markdown_text))):
        original = source_text[index] if index < len(source_text) else None
        output = markdown_text[index] if index < len(markdown_text) else None
        if original != output:
            mismatches.append({'block': index + 1,
                               'source': original[:120] if original else original,
                               'markdown': output[:120] if output else output})

    expected_images = manifest.get('images', [])
    markdown_images = [value for kind, value in converted if kind == 'image']
    source_image_count = sum(kind == 'image' for kind, _ in source)
    image_issues = []
    if source_image_count != len(markdown_images):
        image_issues.append(
            f'記事内画像数 {source_image_count} とMarkdown参照数 {len(markdown_images)} が一致しません')
    if source_image_count != len(expected_images):
        image_issues.append(
            f'記事内画像数 {source_image_count} とmanifest記録数 {len(expected_images)} が一致しません')

    expected_paths = []
    for index, image in enumerate(expected_images):
        path = image.get('path')
        expected_paths.append(path)
        if index >= len(markdown_images) or markdown_images[index] != path:
            image_issues.append(f'画像{index + 1}のMarkdown参照がmanifestと一致しません')
        if not path:
            image_issues.append(f'画像{index + 1}のローカルパスがありません')
            continue
        image_file = out_dir / path
        if not image_file.is_file():
            image_issues.append(f'画像ファイルがありません: {path}')
        elif image.get('sha256') and hashlib.sha256(image_file.read_bytes()).hexdigest() != image['sha256']:
            image_issues.append(f'画像ファイルのSHA-256が一致しません: {path}')

    expected_events = []
    for kind, value in source:
        if kind == 'image':
            path = expected_paths[value - 1] if value <= len(expected_paths) else None
            expected_events.append(('image', path))
        else:
            expected_events.append((kind, value))
    placement_matches = expected_events == converted
    checks = {
        'text': {
            'status': 'PASS' if not mismatches else 'FAIL',
            'source_blocks': len(source_text),
            'markdown_blocks': len(markdown_text),
            'mismatches': mismatches[:10],
            'mismatch_count': len(mismatches),
        },
        'images': {
            'status': 'PASS' if not image_issues else 'FAIL',
            'source_count': source_image_count,
            'markdown_count': len(markdown_images),
            'manifest_count': len(expected_images),
            'issues': image_issues,
        },
        'placement': {
            'status': 'PASS' if placement_matches else 'FAIL',
            'source_order': [value for kind, value in expected_events if kind == 'image'],
            'markdown_order': [value for kind, value in converted if kind == 'image'],
        },
    }
    return checks


def render_check_report(chapters):
    lines = ['# KDP原稿チェックレポート', '']
    for chapter in chapters:
        checks = chapter['checks']
        statuses = [check['status'] for check in checks.values()]
        overall = 'PASS' if all(status == 'PASS' for status in statuses) else '要確認'
        lines.extend([f'## {chapter["title"]} - {overall}', '',
                      f'- 公開記事: {chapter["url"]}',
                      f'- 本文: {checks["text"]["status"]} '
                      f'（公開記事 {checks["text"]["source_blocks"]} ブロック / '
                      f'Markdown {checks["text"]["markdown_blocks"]} ブロック）',
                      f'- 画像: {checks["images"]["status"]} '
                      f'（記事 {checks["images"]["source_count"]} 枚 / '
                      f'Markdown {checks["images"]["markdown_count"]} 参照 / '
                      f'ローカル記録 {checks["images"]["manifest_count"]} 枚）',
                      f'- 画像順序・挿入位置: {checks["placement"]["status"]}',])
        for mismatch in checks['text']['mismatches']:
            lines.append(f'  - 本文ブロック {mismatch["block"]}: '
                         f'公開記事={mismatch["source"]!r} / '
                         f'Markdown={mismatch["markdown"]!r}')
        for issue in checks['images']['issues']:
            lines.append(f'  - 画像: {issue}')
        if checks['text']['mismatch_count'] > len(checks['text']['mismatches']):
            lines.append(f'  - 本文差分は他に '
                         f'{checks["text"]["mismatch_count"] - len(checks["text"]["mismatches"])} 件あります')
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def convert_article(html, url, out_dir, session, download_images=True,
                    image_offset=0, image_dir=None, markdown_path=None):
    soup = BeautifulSoup(html, 'html.parser')
    article = clean_article(select_article(soup))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'source_article.html').write_text(str(article), encoding='utf-8')
    blocks = flatten_blocks(article)
    result = []
    images = []
    issues = []
    for block in blocks:
        kind = block[0]
        if kind == 'heading':
            result.append('#' * block[1] + ' ' + block[2])
        elif kind == 'paragraph':
            result.append(block[1])
        elif kind == 'list':
            result.append('- ' + block[1])
        elif kind == 'rule':
            result.append('---')
        elif kind == 'image':
            img = block[1]
            src = image_url(img,url)
            if not src:
                issues.append('Image without downloadable URL')
                continue
            item = {'ordinal':len(images)+1,'source_url':src,'alt':img.get('alt','')}
            if download_images:
                try:
                    data=fetch(session,src)
                    fname=safe_image_name(image_offset+len(images)+1,src,data)
                    imdir=Path(image_dir) if image_dir else out_dir/'images'
                    imdir.mkdir(parents=True,exist_ok=True)
                    (imdir/fname).write_bytes(data)
                    item['path']=fname if image_dir else 'images/'+fname
                    item['sha256']=hashlib.sha256(data).hexdigest()
                    result.append(f'![{item["alt"]}]({item["path"]})')
                except requests.RequestException as exc:
                    issues.append(f'Image download failed: {src}: {exc}')
                    result.append(f'<!-- MISSING IMAGE: {src} -->')
            else:
                item['path']=None
                result.append(f'![{item["alt"]}]({src})')
            images.append(item)
    markdown_file=Path(markdown_path) if markdown_path else out_dir/'chapter.md'
    markdown_file.parent.mkdir(parents=True,exist_ok=True)
    markdown_file.write_text('\n\n'.join(result).rstrip()+'\n', encoding='utf-8')
    info={'url':url,'source_html_sha256':hashlib.sha256(html).hexdigest(),
          'source_block_count':len(blocks),'markdown_block_count':len(result),
          'image_count':len(images),'images':images,'warnings':issues}
    (out_dir/'manifest.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    return info


def build(config, base):
    session=requests.Session(); session.headers.update({'User-Agent':USER_AGENT})
    root=base/'output'/config.get('slug','book')
    root.mkdir(parents=True,exist_ok=True)
    export_dir=root/'den-den'
    verification_dir=root/'verification'
    export_dir.mkdir(parents=True,exist_ok=True)
    verification_dir.mkdir(parents=True,exist_ok=True)
    all_chapters=[]; report=[]; image_offset=0
    for i,ch in enumerate(config['chapters'],1):
        url=ch['url']; data=fetch(session,url)
        folder=verification_dir/f'chapter_{i:02d}'
        folder.mkdir(exist_ok=True)
        (folder/'source_page.html').write_bytes(data)
        with tempfile.TemporaryDirectory() as temp_dir:
            chapter_markdown=Path(temp_dir)/'chapter.md'
            info=convert_article(data,url,folder,session,image_offset=image_offset,
                                 image_dir=export_dir,markdown_path=chapter_markdown)
            md=chapter_markdown.read_text(encoding='utf-8')
        image_offset += info['image_count']
        info['title']=ch['title']; report.append(info)
        info['checks']=validate_chapter(data,md,export_dir,info)
        all_chapters.append(md)
    manuscript=f'# {config["title"]}\n\n'+'\n\n'.join(all_chapters)
    (export_dir/'manuscript.md').write_text(manuscript,encoding='utf-8')
    report_file=verification_dir/'report.json'
    report_file.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    check_report=verification_dir/'check_report.md'
    check_report.write_text(render_check_report(report),encoding='utf-8')
    archive=root/'den-den.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
        members={'manuscript.md'}
        members.update(image['path'] for entry in report for image in entry['images']
                       if image.get('path'))
        for name in sorted(members):
            path=export_dir/name
            if path.is_file():
                bundle.write(path,arcname=path.name)
    cover_image=config.get('cover_image')
    if cover_image:
        create_kdp_cover(export_dir/cover_image,config['title'],config.get('author',''),
                         root/'cover.jpg')
    warnings=[w for entry in report for w in entry['warnings']]
    for entry in report:
        for name,check in entry['checks'].items():
            if check['status'] == 'FAIL':
                warnings.append(f'{entry["title"]}: {name} validation failed')
    cover_output=f' | Cover: {root/"cover.jpg"}' if cover_image else ''
    print(f'Output: {export_dir} | Archive: {archive}{cover_output} | chapters={len(report)} | images={image_offset} | warnings={len(warnings)}')
    if warnings:
        for w in warnings: print('WARNING:',w,file=sys.stderr)
        return 2
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='books/gadegal-zero-01/book.yaml')
    args=parser.parse_args()
    base=Path(__file__).resolve().parent
    config=yaml.safe_load((base/args.config).read_text(encoding='utf-8'))
    return build(config,base)

if __name__=='__main__': raise SystemExit(main())
