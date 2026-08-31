#!/bin/zsh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.auto-aivtuber.post"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$LABEL.plist"
HOUR="$(awk -F= '/^AUTO_POST_HOUR=/{print $2}' "$ROOT/.env" 2>/dev/null | tr -d '[:space:]')"
MINUTE="$(awk -F= '/^AUTO_POST_MINUTE=/{print $2}' "$ROOT/.env" 2>/dev/null | tr -d '[:space:]')"
HOUR="${HOUR:-21}"
MINUTE="${MINUTE:-00}"

if [[ ! -x "$ROOT/run_auto.sh" ]]; then
  chmod +x "$ROOT/run_auto.sh"
fi
mkdir -p "$PLIST_DIR"

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT/run_auto.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>$HOUR</integer>
    <key>Minute</key>
    <integer>$MINUTE</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>$ROOT/output/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/output/launchd.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
print "自動投稿を登録しました: 毎日 ${HOUR}:${MINUTE}"
print "停止: launchctl bootout gui/$(id -u) $PLIST_PATH"
