#!/bin/bash
# kaya-vocab を GitHub Pages にデプロイする

set -e

DEPLOY_DIR="/tmp/kaya-vocab-deploy"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== kaya-vocab デプロイ ==="
echo "ソース: $SOURCE_DIR"

# 変更ファイルをデプロイ用リポジトリにコピー
cp -r "$SOURCE_DIR/." "$DEPLOY_DIR/"

cd "$DEPLOY_DIR"

# 変更があるか確認
if git diff --quiet && git diff --cached --quiet; then
  echo "変更なし。デプロイ不要。"
  exit 0
fi

# コミットメッセージを引数から取得（なければ日付）
MSG="${1:-Update $(date '+%Y-%m-%d %H:%M')}"

git add .
git commit -m "$MSG"
git push

echo ""
echo "✅ デプロイ完了！"
echo "   https://mokasz.github.io/kaya-vocab/"
