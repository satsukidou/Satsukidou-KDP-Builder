import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import Mock, patch
from zipfile import ZipFile
from PIL import Image
from cover import (build_cover_metadata, build_cover_prompt,
                   create_kdp_cover, generate_cover_package,
                   select_cover_candidates)
from builder import (build, convert_article, image_url, select_article,
                     flatten_blocks, validate_chapter)
from bs4 import BeautifulSoup

HTML = '''<html><body><nav>Do not include me</nav><article><div class="entry-content">
<h2>第一話「空が消えた日」</h2><p>「コーヒー、いかがですか？」</p>
<figure><img src="https://example.org/uploads/one.png" alt="coffee"><figcaption>珈琲</figcaption></figure>
<p>紗月は、淹れたてのコーヒーをデスクに置いた。</p>
<div class="wp-block-image"><figure><img data-src="https://example.org/uploads/two.jpg" src="data:image/png;base64,xx"></figure></div>
<p>そして、宇宙船が現れた。</p></div></article><footer>Do not include me</footer></body></html>'''
class BuilderTests(unittest.TestCase):
 def test_body_selection(self):
  body=select_article(BeautifulSoup(HTML,'html.parser'))
  self.assertNotIn('Do not include',body.get_text())
 def test_order_and_images(self):
  session=Mock(); session.get.side_effect=lambda url,timeout: Mock(content=b'fakeimage',raise_for_status=lambda:None)
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp)
   info=convert_article(HTML.encode(),'https://example.org/post/',folder,session)
   txt=(folder/'chapter.md').read_text()
   self.assertEqual(info['image_count'],2)
   self.assertEqual(info['warnings'],[])
   self.assertLess(txt.index('コーヒー、いかが'),txt.index('image_001'))
   self.assertLess(txt.index('image_001'),txt.index('紗月は'))
   self.assertLess(txt.index('紗月は'),txt.index('image_002'))
   self.assertLess(txt.index('image_002'),txt.index('宇宙船が現れた'))
   self.assertEqual(len(list((folder/'images').iterdir())),2)
   self.assertTrue((folder/'source_article.html').exists())
  self.assertIn('コーヒー',info['images'][0]['context'])
 def test_missing_image_reports_failure(self):
  session=Mock(); session.get.side_effect=__import__('requests').ConnectionError('offline')
  with tempfile.TemporaryDirectory() as tmp:
   result=convert_article(HTML.encode(),'https://example.org/post/',Path(tmp),session)
   self.assertEqual(len(result['warnings']),2)
 def test_validation_detects_text_image_and_file_changes(self):
  session=Mock(); session.get.side_effect=lambda url,timeout: Mock(content=b'fakeimage',raise_for_status=lambda:None)
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp)
   manifest=convert_article(HTML.encode(),'https://example.org/post/',folder,session)
   markdown=(folder/'chapter.md').read_text(encoding='utf-8')
   checks=validate_chapter(HTML.encode(),markdown,folder,manifest)
   self.assertEqual([check['status'] for check in checks.values()],['PASS','PASS','PASS'])

   edited=markdown.replace('コーヒー、いかがですか？','コーヒー')
   checks=validate_chapter(HTML.encode(),edited,folder,manifest)
   self.assertEqual(checks['text']['status'],'FAIL')

   images=[image['path'] for image in manifest['images']]
   swapped=markdown.replace(images[0],'__IMAGE__').replace(images[1],images[0]).replace('__IMAGE__',images[1])
   checks=validate_chapter(HTML.encode(),swapped,folder,manifest)
   self.assertEqual(checks['images']['status'],'FAIL')
   self.assertEqual(checks['placement']['status'],'FAIL')

   (folder/images[0]).unlink()
   checks=validate_chapter(HTML.encode(),markdown,folder,manifest)
   self.assertEqual(checks['images']['status'],'FAIL')
   self.assertTrue(any('画像ファイルがありません' in issue for issue in checks['images']['issues']))

 def test_cover_metadata_candidates_and_prompt(self):
  with tempfile.TemporaryDirectory() as tmp:
   image_root=Path(tmp)
   Image.new('RGB',(1000,1600),(30,40,60)).save(image_root/'image_001.png')
   Image.new('RGB',(1200,800),(30,100,180)).save(image_root/'image_004.png')
   chapters=[
    {'title':'第一話「空が消えた日」','url':'https://example.org/zero-1/','images':[
     {'path':'image_001.png','source_url':'https://example.org/one.png','alt':'',
      'context':'オフィスで紗月がコーヒーを飲む'}]},
    {'title':'第二話「光の向こうへ」','url':'https://example.org/zero-02/','images':[
     {'path':'image_004.png','source_url':'https://example.org/異星母艦の光に舞う三人.png','alt':'',
      'context':'三人が青白い光に包まれる'}]},
   ]
   candidates=select_cover_candidates(chapters,image_root,count=2)
   self.assertEqual([item['image_path'] for item in candidates],['image_004.png','image_001.png'])
   config={'title':'がでがる ZERO 〜最初の一滴〜','author':'紗月堂','cover':{
    'summary':'三人が巨大宇宙船と出会い、日常から非日常へ踏み出す。',
    'characters':['紗月','ルナ','ティルス'],'motifs':['コーヒー','巨大宇宙船','青白い光']}}
   metadata=build_cover_metadata(config,chapters,candidates)
   prompt=build_cover_prompt(metadata,candidates[0],2)
   self.assertEqual(metadata['title'],'がでがる ZERO')
   self.assertEqual(metadata['subtitle'],'最初の一滴')
   self.assertEqual(len(metadata['episodes']),2)
   self.assertIn('https://example.org/zero-1/',str(metadata['episodes']))
   self.assertIn('紗月・ルナ・ティルス',prompt)
   self.assertIn('image_004.png',prompt)
   self.assertIn('1600:2560',prompt)

 def test_cover_package_writes_drafts_and_selected_final(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   image_root=root/'images'
   image_root.mkdir()
   Image.new('RGB',(1000,1600),(30,40,60)).save(image_root/'image_001.png')
   Image.new('RGB',(1200,800),(30,100,180)).save(image_root/'image_004.png')
   chapters=[
    {'title':'第一話','url':'https://example.org/zero-1/','images':[
     {'path':'image_001.png','source_url':'https://example.org/one.png','context':'オフィスとコーヒー'}]},
    {'title':'第二話','url':'https://example.org/zero-02/','images':[
     {'path':'image_004.png','source_url':'https://example.org/異星母艦の光に舞う三人.png','context':'三人と青白い光'}]},
   ]
   config={'title':'がでがる ZERO 〜最初の一滴〜','author':'紗月堂','cover':{
    'draft_count':2,'use_web_images':True,'include_title_text':False,
    'format':'jpg','width':800,'height':1280,'summary':'三人が宇宙船へ導かれる。',
    'characters':['紗月','ルナ','ティルス'],'motifs':['コーヒー','光'],
    'selected_cover':'cover_draft_02.jpg','output_final_name':'cover_final.jpg'}}
   output=root/'cover'
   result=generate_cover_package(config,chapters,image_root,output)
   self.assertEqual(len(result['drafts']),2)
   self.assertEqual(len(result['prompts']),2)
   self.assertTrue((output/'cover_prompt.txt').is_file())
   self.assertTrue((output/'cover_prompt_01.txt').is_file())
   self.assertTrue((output/'cover_prompt_02.txt').is_file())
   self.assertFalse((output/'cover_prompt_03.txt').exists())
   self.assertTrue((output/'cover_metadata.json').is_file())
   self.assertEqual((output/'cover_draft_02.jpg').read_bytes(),
                    (output/'cover_final.jpg').read_bytes())
   with Image.open(output/'cover_draft_01.jpg') as draft:
    self.assertEqual(draft.size,(800,1280))

 def test_cover_art_fills_canvas_without_inset_frame(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   source=root/'source.png'
   output=root/'cover.jpg'
   Image.new('RGB',(100,160),(190,30,25)).save(source)
   create_kdp_cover(source,'Test','Author',output,include_title_text=False)
   with Image.open(output) as cover:
    self.assertEqual(cover.size,(1600,2560))
    red,green,blue=cover.convert('RGB').getpixel((800,944))
    self.assertGreater(red,blue)

 def test_build_cover_can_be_disabled(self):
  image_buffer=io.BytesIO()
  Image.new('RGB',(64,36),(35,105,150)).save(image_buffer,format='PNG')
  image_data=image_buffer.getvalue()
  def fake_fetch(session,url,timeout=30):
   return HTML.encode() if url=='https://example.org/post/' else image_data
  config={'slug':'no-cover-book','title':'Test','cover':{'enabled':False},
          'chapters':[{'title':'第一話','url':'https://example.org/post/'}]}
  with tempfile.TemporaryDirectory() as tmp, patch('builder.fetch',side_effect=fake_fetch):
   with redirect_stdout(io.StringIO()):
    result=build(config,Path(tmp))
   output=Path(tmp)/'output'/'no-cover-book'
   self.assertEqual(result,0)
   self.assertFalse((output/'cover').exists())
   self.assertFalse((output/'cover.jpg').exists())

 def test_build_writes_check_report(self):
  image_buffer=io.BytesIO()
  Image.new('RGB',(64,36),(35,105,150)).save(image_buffer,format='PNG')
  image_data=image_buffer.getvalue()
  def fake_fetch(session,url,timeout=30):
   return HTML.encode() if url=='https://example.org/post/' else image_data
  config={'slug':'test-book','title':'がでがる ZERO 〜最初の一滴〜','author':'紗月堂',
          'cover_image':'image_002.png',
          'chapters':[{'title':'第一話','url':'https://example.org/post/'}]}
  tmp=Path(tempfile.mkdtemp())
  self.addCleanup(shutil.rmtree,tmp)
  with patch('builder.fetch',side_effect=fake_fetch):
   with redirect_stdout(io.StringIO()):
    result=build(config,tmp)
  root=tmp/'output'/'test-book'
  export=root/'den-den'
  verification=root/'verification'
  report=(verification/'check_report.md').read_text(encoding='utf-8')
  details=json.loads((verification/'report.json').read_text(encoding='utf-8'))
  self.assertEqual(result,0)
  self.assertIn('本文: PASS',report)
  self.assertIn('画像順序・挿入位置: PASS',report)
  self.assertEqual(details[0]['checks']['text']['status'],'PASS')
  markdown=(export/'manuscript.md').read_text(encoding='utf-8')
  self.assertIn('](image_001.png)',markdown)
  self.assertIn('](image_002.png)',markdown)
  self.assertLess(markdown.index('image_001.png'),markdown.index('紗月は'))
  self.assertLess(markdown.index('紗月は'),markdown.index('image_002.png'))
  with ZipFile(root/'den-den.zip') as bundle:
   self.assertEqual(sorted(bundle.namelist()),['image_001.png','image_002.png','manuscript.md'])
   self.assertTrue(all('/' not in name for name in bundle.namelist()))
  self.assertTrue((verification/'chapter_01'/'source_page.html').is_file())
  self.assertTrue((verification/'chapter_01'/'source_article.html').is_file())
  with Image.open(root/'cover.jpg') as cover:
   self.assertEqual(cover.format,'JPEG')
   self.assertEqual(cover.size,(1600,2560))
   self.assertEqual(cover.mode,'RGB')
  self.assertLess((root/'cover.jpg').stat().st_size,50*1024*1024)
if __name__=='__main__': unittest.main()
