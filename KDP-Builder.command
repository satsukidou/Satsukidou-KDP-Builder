#!/bin/bash

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULT=0

if ! cd "$PROJECT_DIR"; then
    echo "プロジェクトフォルダへ移動できません: $PROJECT_DIR"
    RESULT=1
elif [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="$(command -v python3)"
else
    echo "Python 3 が見つかりません。Python 3をインストールしてください。"
    RESULT=127
fi

if [[ "$RESULT" -eq 0 ]]; then
    echo "実行フォルダ: $PROJECT_DIR"
    echo "Python: $PYTHON"
    "$PYTHON" "$PROJECT_DIR/builder.py" "$@"
    RESULT=$?
fi

if [[ "$RESULT" -eq 0 ]]; then
    echo "KDP Builderは正常に終了しました。"
else
    echo "KDP Builderはエラーコード $RESULT で終了しました。上のエラー内容を確認してください。"
fi

read -r -p "結果を確認したらEnterキーを押してください..." _
exit "$RESULT"