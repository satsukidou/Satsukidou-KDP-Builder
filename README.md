# 紗月堂 KDP Builder (MVP v0.1)

WordPress公開記事の本文・挿絵を順番どおりにローカルへ保存する小さなPythonツール。

## Quick start

```bash
python -m pip install -r requirements.txt
python builder.py --config books/gadegal-zero-01/book.yaml
python -m unittest discover -s tests -v
```

出力：`output/gadegal-zero-01/den-den/`に`manuscript.md`と連番画像、同階層の内容をまとめた`den-den.zip`。KDP電子書籍用の表紙は`cover.jpg`として別に生成します。公開ページHTML・記事HTML・manifest・本文/画像チェックレポートは`verification/`に分けて保存します。ZIPを展開するとMarkdownと画像が同じ階層に並び、検証用ファイルは含まれません。

**注意：** 現状はHTML→Markdown変換のMVPです。検証レポートは抽出した本文ブロック、画像ファイル・順序・挿入位置を比較しますが、Markdownの文字組・強調やリンク、改行を100%再現する保証はありません。WordPressテーマ固有の構造によっては抽出範囲の調整が必要です。`verification/check_report.md`と`report.json`を確認してください。画像が取得できないときは警告を出し、正常完了とは扱いません。

トップのアイキャッチは通常記事本文とは別要素です。アイキャッチも自動取得したい場合は次版でWordPressメタデータ対応を追加します。KDP用正式表紙・EPUB生成・Kindleプレビュー・KDP登録は未実装です。
