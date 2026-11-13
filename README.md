# geekbench-local-lens

Run Geekbench **entirely on your own machine**: benchmark locally, keep the
result, never touch the vendor's browser.

[中文说明](README.zh-CN.md) · [How it works](docs/how-it-works.md) · [Platforms](docs/platforms.md) · [Pitfalls](docs/pitfalls.md) · [Agent usage](docs/agent-usage.md)

---

## Why

The free Geekbench 7 build has two properties that make local benchmarking
awkward:

1. It requires a live internet connection and uploads every result to the
   Geekbench Browser automatically (`--no-upload` is a Pro-only switch).
2. Its **result window is a web view of the browser page** — the score table
   is rendered server-side, not locally.

So "just block the upload" gives you a benchmark that runs and then shows
*"Unable to display benchmark results"*. This project takes the other route:
let the upload succeed, but point it at `127.0.0.1`. The client is happy, the
data never leaves the machine, and the result is rendered locally.

```
Geekbench 7 (patched copy)
   │  POST http://127.0.0.1:8080/   multipart: document + hash
   ▼
gblens serve  ──►  results/<id>.json          raw upload
                ──►  results/<id>.document.json  extracted result
                ──►  results/<id>.html         locally rendered page
```

## Install

```bash
git clone https://github.com/<you>/geekbench-local-lens.git
cd geekbench-local-lens
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
gblens doctor          # environment self-check (JSON with --json)
```

Requirements: macOS, Python ≥ 3.9, Xcode command line tools (`codesign`,
`PlistBuddy`). No third-party dependencies.

## Quick start

```bash
# 1. start the local endpoint (foreground; see scripts/ for a launchd unit)
gblens serve --results ./results --http-port 8080 --open

# 2. clone and patch the app so it uploads to localhost over plain HTTP
gblens patch \
  --app "/Applications/Geekbench 7.app" \
  --out "$HOME/Applications/Geekbench 7 Local.app"

# 3. run it, press "Run CPU Benchmark"
open "$HOME/Applications/Geekbench 7 Local.app"
```

When the benchmark finishes, `results/<timestamp>.html` appears and opens in
your browser. Everything stays on disk.

Want the renderer without patching anything? `gblens view` accepts `.gb6`,
`.gb7` and plain JSON result files — including ones you saved from the
Geekbench Browser:

```bash
gblens view ~/Downloads/result.gb7 --open
```

## What the patch actually changes

| Change | Where | Why |
| --- | --- | --- |
| `browser.geekbench.com` → `127.0.0.1:8080` | main executable, string table | upload goes to localhost |
| conditional `b.ne` → unconditional `b` | URL builder, right before `movk #0x3a73` ("s:" in `https://`) | forces the `http://` branch, so no trusted CA is needed |
| `SUFeedURL` invalidated, auto-update off | `Contents/Info.plist` | the copy must not update itself back to stock |
| ad-hoc re-sign (`--options linker-signed`) | whole bundle | code-segment edits break the original signature |

The patched app is a **copy**. The original in `/Applications` is untouched.

## CLI

```
gblens serve   --results DIR [--http-port 8080] [--https-port 8443 --cert C --key K] [--open]
gblens view    FILE [--html OUT] [--open]
gblens patch   [--app APP] [--out DIR] [--host 127.0.0.1:8080] [--keep-https]
gblens info    [--app APP]
gblens doctor  [--app APP] [--results DIR] [--http-port 8080]
```

Every subcommand accepts `--json` and prints exactly one JSON document.
Exit codes: `0` ok, `1` verification failure, `2` unsupported build.

## For agents

The tool is built to be driven by an agent with no human in the loop:

```bash
gblens --json doctor                       # environment facts
gblens --json patch --out /tmp/gb.app      # {"ok":true,"host_hits":2,...}
gblens --json view results/x.gb7           # {"single":{...},"multi":{...}}
gblens serve --results ./results --json    # prints {"listening":...} then serves
```

See [AGENTS.md](AGENTS.md) for the recommended call sequence, invariants to
assert, and the failure modes worth retrying versus surfacing.

## Limits / known issues

- **The client's own result window still fails** (`Unable to display benchmark
  results`). Our fake endpoint sends a superset JSON, but the client validates
  a field we have not pinned down. The upload has already landed at that point;
  use the rendered HTML.
- `--no-upload`, `--json`, `--save` are Pro-only switches in the CLI; this
  project does not unlock them and does not ship a keygen.
- HTTPS mode (`--https-port`) needs a CA the *client* trusts. On recent macOS
  versions `security add-trusted-cert` from a non-GUI session is silently
  rejected; use the Keychain GUI, or just stay on the HTTP branch.
- The scheme patch depends on the instruction sequence of the current build
  (7.1.0). On a new release `gblens patch` fails loudly (exit 2) instead of
  producing a broken binary.

See [docs/approaches.md](docs/approaches.md) for the full comparison of offline strategies (blackhole, proxy, hooks, response-schema reverse engineering, Pro).

## Cross-platform

Unix-first: macOS is verified end to end, Linux CLI builds are expected to work
unchanged (same byte patterns, no code signing). Windows is welcome as a
contribution — the renderer and server already run there; only the patch
verification is missing.

The layering is deliberate so a port is small: `render.py` and `server.py` are
pure Python, `patch.py` is byte-level and format-agnostic (Mach-O / ELF / PE),
and the only OS-specific step is signing (`codesign` on macOS, no-op elsewhere).

- `gblens scan <binary>` tells you whether a build is patchable before you touch it
- see [docs/platforms.md](docs/platforms.md) for the status matrix
- see [docs/extending.md](docs/extending.md) and
  [docs/agent-extension-prompt.md](docs/agent-extension-prompt.md) to add a
  platform with an agent

## Development

```bash
python3 -m pytest tests/ -q      # or: python3 -m unittest discover -s tests
python3 -m gblens.cli view examples/results/sample-macbook-air-m5.gb7.json
```

Layout:

```
gblens/render.py    schema-tolerant result renderer (terminal + HTML)
gblens/server.py    local upload endpoint (HTTP and optional HTTPS)
gblens/patch.py     host/scheme patching + re-signing
gblens/cli.py       argument parsing, JSON surface, exit codes
docs/               mechanism, pitfalls, agent recipes
```

Contributions welcome — especially new result-schema shapes (Geekbench 5/6/7,
AI, Compute) and Windows/Linux equivalents of the patch layer.

## Acknowledgements

Built inside **DeepSeek Harness** with the **DeepSeek Purge** plugin — the agent
drove the machine, ran the benchmarks and verified each step against live logs.
Details in [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md).

## Disclaimer

Use it on machines you own or are authorised to test. The patch modifies a
copy of a commercial application for local interoperability; it does not
redistribute the application, bypass licensing, or unlock Pro features.

MIT licensed.
