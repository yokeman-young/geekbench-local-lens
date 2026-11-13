# Agent usage recipes

All commands are non-interactive and accept `--json`.

## Health check

```bash
gblens --json doctor
```

Key fields: `app_exists`, `app_version`, `probe` (HTTP status of the endpoint),
`results_count`.

## Full unattended run

```bash
set -euo pipefail
RESULTS="$PWD/results"

gblens serve --results "$RESULTS" --http-port 8080 --open &
SERVER_PID=$!
sleep 1
gblens --json doctor | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["probe"]==200'

OUT=/tmp/gb-local.app
gblens --json patch --app "/Applications/Geekbench 7.app" --out "$OUT" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] and d["host_hits"]>0'

open "$OUT"        # hand to the UI layer
# … wait for results/<ts>.html to appear (poll, don't sleep blindly) …
latest=$(ls -t "$RESULTS"/*.document.json | head -1)
gblens --json view "$latest" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["single"]["score"]>0'
```

## Waiting for a run to finish

```bash
before=$(ls -1 "$RESULTS"/*.html 2>/dev/null | wc -l)
for _ in $(seq 1 120); do
  now=$(ls -1 "$RESULTS"/*.html 2>/dev/null | wc -l)
  [ "$now" -gt "$before" ] && break
  sleep 5
done
```

## Inspecting an unknown build

```bash
gblens --json scan "/Applications/Geekbench 7.app/Contents/MacOS/Geekbench 7"
# {"format":"macho-fat","host_hits":2,"scheme_hits":1,"patchable":true}
```

If `patchable` is false, stop — do not guess at offsets.

## Linux / Windows CLI builds

```bash
gblens scan ./geekbench_x86_64
gblens patch --binary ./geekbench_x86_64 --host 127.0.0.1:8080
gblens serve --results ./results --http-port 8080 &
./geekbench_x86_64 --cpu
```

## Parsing results without the CLI

```python
from gblens import render
report, html = render.render_file("results/x.document.json")
print(report.single["score"], report.multi["score"])
```

## Failure handling

See the table in `AGENTS.md`. In short: retry on port conflicts, stop and report
on `scan.patchable == false`, and treat the client's own "unable to display"
dialog as benign.
