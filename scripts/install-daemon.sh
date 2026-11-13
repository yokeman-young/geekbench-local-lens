#!/bin/bash
# Install (or remove) a per-user LaunchAgent that keeps `gblens serve` running.
#   ./install-daemon.sh [results-dir] [port]
#   ./install-daemon.sh --uninstall
set -euo pipefail

LABEL="local.gblens.serve"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS="${1:-$ROOT/results}"
PORT="${2:-8080}"

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "removed $LABEL"
  exit 0
fi

mkdir -p "$RESULTS" "$(dirname "$PLIST")"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/env</string>
    <string>python3</string>
    <string>-m</string>
    <string>gblens.cli</string>
    <string>serve</string>
    <string>--results</string><string>$RESULTS</string>
    <string>--http-port</string><string>$PORT</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$RESULTS/serve.out</string>
  <key>StandardErrorPath</key><string>$RESULTS/serve.err</string>
</dict>
</plist>
PLISTEOF

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"
sleep 1
curl -s "http://127.0.0.1:$PORT/" -o /dev/null -w "endpoint: %{http_code}\n"
echo "installed $LABEL -> $RESULTS (port $PORT)"
