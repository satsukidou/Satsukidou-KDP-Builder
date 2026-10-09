# 紗月堂 KDP Builder (MVP v0.1)

WordPress公開記事の本文・挿絵を順番どおりにローカルへ保存する小さなPythonツール。

## Quick start

```bash
python -m pip install -r requirements.txt
python builder.py --config books/gadegal-zero-01/book.yaml
python -m unittest discover -s tests -v
```

出力：`output/gadegal-zero-01/den-den/`に`manuscript.md`と連番画像、同階層の内容をまとめた`den-den.zip`。表紙メタデータ、2〜3案のプロンプトとJPGドラフトは`cover/`に分けて出力します。選択済み案を`selected_cover`に指定すると`output_final_name`へコピーします。公開ページHTML・記事HTML・manifest・本文/画像チェックレポートは`verification/`に分けて保存し、原稿ZIPには含めません。

表紙設定は`book.yaml`の`cover`で管理します。設定の`draft_count`・`use_web_images`・`include_title_text`・`width`・`height`で候補と仕様を切り替えられます。画像生成APIは未接続のため、JPGドラフトは取得済み挿絵を組み合わせた比較用案で、`cover_prompt_01.txt`などは外部画像生成サービスへ渡すための指示書です。表紙はKDP電子書籍向け1600×2560px・RGB・JPEG（72 DPI）を初期値とし、50MB未満に収めます。ペーパーバック表紙は背幅を含むフルカバーPDFが別途必要です。

**注意：** 現状はHTML→Markdown変換のMVPです。検証レポートは抽出した本文ブロック、画像ファイル・順序・挿入位置を比較しますが、Markdownの文字組・強調やリンク、改行を100%再現する保証はありません。WordPressテーマ固有の構造によっては抽出範囲の調整が必要です。`verification/check_report.md`と`report.json`を確認してください。画像が取得できないときは警告を出し、正常完了とは扱いません。

トップのアイキャッチは通常記事本文とは別要素です。アイキャッチも自動取得したい場合は次版でWordPressメタデータ対応を追加します。KDP用正式表紙・EPUB生成・Kindleプレビュー・KDP登録は未実装です。
