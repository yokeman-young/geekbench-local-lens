#!/bin/bash
# Smoke test without touching any installed app: serve a fixture and render it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -m gblens.cli view examples/results/sample-macbook-air-m5.gb7.json --html /tmp/gblens-demo.html
python3 -m gblens.cli scan "/Applications/Geekbench 7.app/Contents/MacOS/Geekbench 7" || true
echo "open /tmp/gblens-demo.html"
