# AGENTS.md — driving geekbench-local-lens from an agent

This repository is designed to be operated end-to-end by an automated agent
(Claude Code, Codex, DeepSeek Harness, custom harnesses). Everything an agent
needs is a subprocess call plus a JSON assertion.

## Contract

- **Platform**: macOS 12+. `codesign`, `/usr/libexec/PlistBuddy`, `open` must exist.
- **Runtime**: Python ≥ 3.9, no third-party packages.
- **Never interactive**: no subcommand prompts. `serve` blocks; everything else returns.
- **JSON surface**: add `--json` to any subcommand (`gblens --json …` or `gblens … --json`).
  Each call prints exactly one JSON document on stdout.
- **Exit codes**: `0` success, `1` verification failure, `2` unsupported build/structure.
- **Idempotent**: `patch` always writes a fresh clone to `--out`; re-running is safe.
  The source app is only read.

## Recommended sequence

```bash
# 0. facts first — never guess the version
gblens --json doctor
# {"app_version":"7.1.0","probe":"unreachable: …","results_count":0,...}

# 1. start the endpoint (background job, capture the port)
gblens serve --results ./results --http-port 8080 --open &
# expected log line: "listening on 127.0.0.1 (8080); results -> …"

# 2. patch a copy (never patch /Applications in place)
gblens --json patch --app "/Applications/Geekbench 7.app" --out /tmp/gb-local.app
# assert: .ok == true, .host_hits >= 1, .signed == true

# 3. hand the app to the user/UI layer, or drive it if you have UI automation
open /tmp/gb-local.app

# 4. after the run, read the result
ls results/*.html | tail -1
gblens --json view "$(ls -t results/*.document.json | head -1)"
# assert: .single.score > 0 and .multi.score > 0
```

## Assertions worth making

| Step | Assert | Meaning |
| --- | --- | --- |
| doctor | `.app_exists == true` | app path correct |
| doctor | `.probe == 200` after serve | endpoint reachable |
| patch | `.host_hits == 2` | both slices (arm64 + x86_64) rewritten |
| patch | `.scheme_hits >= 1` | http branch forced |
| patch | `.signed == true` | re-sign accepted |
| view | `.single.score` and `.multi.score` non-null | schema recognised |

## Failure modes

| Symptom | Cause | Action |
| --- | --- | --- |
| `patch` exit 2, `host string not found` | new Geekbench build changed the string table | stop, report version; do not fall back to a regex |
| `patch` exit 2, `scheme patch 失败` | instruction sequence changed | run with `--keep-https` (needs trusted CA) or report |
| `codesign` prints `strict validation` | code-segment edit signed without `linker-signed` | already handled; if it reappears, file a bug |
| `serve` binds `Address already in use` | previous instance alive | `lsof -i :8080`, kill, retry |
| upload never arrives | app still points at the vendor host | re-run `patch`, verify `gblens info` executable path |
| client shows *Unable to display benchmark results* | expected: response schema unknown | ignore; the upload already landed, use the HTML |
| `security add-trusted-cert` returns 0 but trust settings stay empty | TCC blocks non-GUI sessions | do not loop; either use Keychain GUI or stay on HTTP |

## Safety boundaries

- Results and uploads must stay under `--results`; never POST to a remote host.
- The patch is applied to a clone under `--out`; do not modify `/Applications`.
- Do not attempt to unlock Pro features (`--no-upload`, `--save`, `--json` in the
  client CLI). This project deliberately does not implement licence bypass.
- If a harness runs with a file sandbox, `codesign` and `PlistBuddy` need write
  access to `--out` and read access to the source app.

## Non-goals

- Windows/Linux patching (welcome as a contribution; the renderer is portable).
- Rendering the vendor's exact HTML — we render an equivalent page from the
  uploaded document instead.
