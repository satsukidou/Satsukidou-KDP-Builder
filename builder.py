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
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup, NavigableString, Tag

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
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix not in ('.jpg','.jpeg','.png','.gif','.webp','.avif'):
        suffix = '.img'
    return f'image_{index:03d}_{hashlib.sha256(content).hexdigest()[:10]}{suffix}'


def convert_article(html, url, out_dir, session, download_images=True):
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
                    fname=safe_image_name(len(images)+1,src,data)
                    imdir=out_dir/'images'; imdir.mkdir(exist_ok=True)
                    (imdir/fname).write_bytes(data)
                    item['path']='images/'+fname
                    item['sha256']=hashlib.sha256(data).hexdigest()
                    result.append(f'![{item["alt"]}]({item["path"]})')
                except requests.RequestException as exc:
                    issues.append(f'Image download failed: {src}: {exc}')
                    result.append(f'<!-- MISSING IMAGE: {src} -->')
            else:
                item['path']=None
                result.append(f'![{item["alt"]}]({src})')
            images.append(item)
    (out_dir/'chapter.md').write_text('\n\n'.join(result).rstrip()+'\n', encoding='utf-8')
    info={'url':url,'source_html_sha256':hashlib.sha256(html).hexdigest(),
          'source_block_count':len(blocks),'markdown_block_count':len(result),
          'image_count':len(images),'images':images,'warnings':issues}
    (out_dir/'manifest.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    return info


def build(config, base):
    session=requests.Session(); session.headers.update({'User-Agent':USER_AGENT})
    root=base/'output'/config.get('slug','book')
    root.mkdir(parents=True,exist_ok=True)
    all_chapters=[]; report=[]
    for i,ch in enumerate(config['chapters'],1):
        url=ch['url']; data=fetch(session,url)
        folder=root/f'chapter_{i:02d}'
        folder.mkdir(exist_ok=True)
        (folder/'source_page.html').write_bytes(data)
        info=convert_article(data,url,folder,session)
        info['title']=ch['title']; report.append(info)
        md=(folder/'chapter.md').read_text(encoding='utf-8')
        # Relative image links must be anchored at the combined Markdown root.
        md=re.sub(r'\]\(images/', f'](chapter_{i:02d}/images/', md)
        all_chapters.append(md)
    manuscript=f'# {config["title"]}\n\n'+'\n\n'.join(all_chapters)
    (root/'manuscript.md').write_text(manuscript,encoding='utf-8')
    report_file=root/'report.json'
    report_file.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    warnings=[w for entry in report for w in entry['warnings']]
    print(f'Output: {root} | chapters={len(report)} | images={sum(x["image_count"] for x in report)} | warnings={len(warnings)}')
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
