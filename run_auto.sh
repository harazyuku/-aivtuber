#!/bin/zsh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOCK_DIR="/tmp/auto-aivtuber.lock"
LOG_FILE="$ROOT/output/automation.log"

mkdir -p "$ROOT/output"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  print -u2 "別の自動投稿が実行中のため終了します。"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

cd "$ROOT"
exec >> "$LOG_FILE" 2>&1
print "[$(date '+%Y-%m-%d %H:%M:%S')] 自動投稿を開始"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="$(command -v python3)"
fi

if [[ -z "$PYTHON" ]]; then
  print -u2 "python3が見つかりません。"
  exit 1
fi

"$PYTHON" "$ROOT/main.py"
print "[$(date '+%Y-%m-%d %H:%M:%S')] 自動投稿が完了"
