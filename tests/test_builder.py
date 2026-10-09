import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from builder import convert_article, image_url, select_article, flatten_blocks
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
if __name__=='__main__': unittest.main()
