# 紗月堂 KDP Builder (MVP v0.1)

WordPress公開記事の本文・挿絵を順番どおりにローカルへ保存する小さなPythonツール。

## Quick start

```bash
python -m pip install -r requirements.txt
python builder.py --config books/gadegal-zero-01/book.yaml
python -m unittest discover -s tests -v
```

出力：`output/gadegal-zero-01/manuscript.md`、各章の`chapter.md`、`images/`、`source_page.html`、`source_article.html`、`manifest.json`、全体`report.json`。

**注意：** 現状はHTML→Markdown変換のMVPです。原ページHTMLは保存しますが、Markdownの文字組・強調やリンク、改行を100%再現する保証はありません。WordPressテーマ固有の構造によっては抽出範囲の調整が必要です。`report.json`の警告を確認し、公開原稿と目視で比較してください。画像が取得できないときは警告を出し、正常完了とは扱いません。

トップのアイキャッチは通常記事本文とは別要素です。アイキャッチも自動取得したい場合は次版でWordPressメタデータ対応を追加します。KDP用正式表紙・EPUB生成・Kindleプレビュー・KDP登録は未実装です。
