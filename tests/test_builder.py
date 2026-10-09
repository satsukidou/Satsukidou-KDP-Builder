import io
import json
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import Mock, patch
from zipfile import ZipFile
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

 def test_build_writes_check_report(self):
  def fake_fetch(session,url,timeout=30):
   return HTML.encode() if url=='https://example.org/post/' else b'\x89PNG\r\n\x1a\nfakeimage'
  config={'slug':'test-book','title':'Test','chapters':[{'title':'第一話','url':'https://example.org/post/'}]}
  with tempfile.TemporaryDirectory() as tmp, patch('builder.fetch',side_effect=fake_fetch):
   with redirect_stdout(io.StringIO()):
    result=build(config,Path(tmp))
   root=Path(tmp)/'output'/'test-book'
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
if __name__=='__main__': unittest.main()
