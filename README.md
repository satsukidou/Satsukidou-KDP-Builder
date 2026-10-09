# 紗月堂 KDP Builder (MVP v0.1)

WordPress公開記事の本文・挿絵を順番どおりにローカルへ保存する小さなPythonツール。

## Quick start

```bash
python -m pip install -r requirements.txt
python builder.py --config books/gadegal-zero-01/book.yaml
python -m unittest discover -s tests -v
```

## Desktop launchers

macOSでは`KDP-Builder.command`、Windowsでは`KDP-Builder.bat`をダブルクリックするとビルドを開始します。起動ファイルのあるプロジェクトフォルダを作業場所として使い、`.venv`があればそのPythonを優先します。なければmacOSは`python3`、Windowsは`py -3`、次に`python`を使います。実行ログとエラーはターミナルに表示され、終了後はキー入力までウィンドウを開いたままにします。

macOSで起動を拒否された場合は、プロジェクトフォルダで一度だけ次を実行して実行権限を付けてください。

```bash
chmod +x KDP-Builder.command
```

初回はOSごとに`.venv`を作成し、依存パッケージを入れてください。既に`.venv`がある場合も、依存関係が未導入なら同じコマンドで補えます。

macOS:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Windows用`.bat`はmacOSでは実行できません。Windowsで利用するときはWindows上でPythonと依存パッケージを準備し、Windows用の`.venv`を作成してください。

出力：`output/gadegal-zero-01/den-den/`に`manuscript.md`と連番画像、同階層の内容をまとめた`den-den.zip`。手動入力した表紙画像は`output/gadegal-zero-01/cover/cover_final.jpg`へ整形し、全体確認用の`cover_preview.jpg`も出力します。公開ページHTML・記事HTML・manifest・本文/画像チェックレポートは`verification/`に分けて保存し、原稿ZIPには含めません。

表紙画像は`books/gadegal-zero-01/cover/`へ1枚置きます。複数ある場合は`book.yaml`の`cover.input_filename`でファイルを指定してください。`fit_mode: contain`は画像全体を保ち、余った部分を元画像由来のぼかし背景で補います。`fit_mode: cover`は比率を保ったまま中央をトリミングします。元画像は変更せず、1600×2560px・RGB・JPEGの`cover_final.jpg`と、全体表示の800×1280pxプレビューを出力します。最終JPGは50MiB以下に圧縮し、上限を超える場合はエラーにします。画像生成API接続は将来の拡張項目です。ペーパーバック表紙は背幅を含むフルカバーPDFが別途必要です。

**注意：** 現状はHTML→Markdown変換のMVPです。検証レポートは抽出した本文ブロック、画像ファイル・順序・挿入位置を比較しますが、Markdownの文字組・強調やリンク、改行を100%再現する保証はありません。WordPressテーマ固有の構造によっては抽出範囲の調整が必要です。`verification/check_report.md`と`report.json`を確認してください。画像が取得できないときは警告を出し、正常完了とは扱いません。

トップのアイキャッチは通常記事本文とは別要素です。アイキャッチも自動取得したい場合は次版でWordPressメタデータ対応を追加します。KDP用正式表紙・EPUB生成・Kindleプレビュー・KDP登録は未実装です。
