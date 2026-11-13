# Agent prompt: run Geekbench 7 locally with geekbench-local-lens

Copy everything below the line into an agent session (Claude Code, Codex,
DeepSeek Harness, …). It is written to be executed, not discussed.

---

You are operating a local machine (macOS, Linux, or Windows). Your objective:
**produce a Geekbench 7 benchmark result that never leaves this host, and hand
the user a rendered score page.**

Hard rules — violating any of these fails the task:

1. Never modify an installed application in place. `gblens patch` always writes a
   copy; do not "fix" that.
2. Never let results reach a remote host. The endpoint is `127.0.0.1` only.
3. Do not bypass licensing (no Pro switches, no keygen). If the user asks, say
   it is out of scope and continue.
4. Every claim you make must come from a command you actually ran. No guessing
   offsets, no "should work".
5. If a check fails, follow the failure table at the end. Do not improvise
   binary edits.

## Step 0 — install and inspect

```bash
git clone https://github.com/yokeman-young/geekbench-local-lens.git
cd geekbench-local-lens
python3 -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .
gblens --json doctor
```

Assert: `app_exists == true` (macOS) or the CLI binary exists (Linux/Windows).
Record `app_version` — you will need it in the final report.

## Step 1 — decide the platform branch

### macOS (verified)

```bash
gblens --json scan "/Applications/Geekbench 7.app/Contents/MacOS/Geekbench 7"
# expect: {"format":"macho-fat","host_hits":2,"scheme_hits":1,"patchable":true}

gblens --json patch \
  --app "/Applications/Geekbench 7.app" \
  --out "$HOME/Applications/Geekbench 7 Local.app"
# expect: ok=true, host_hits=2, scheme_hits=1, signed=true
```

If `host_hits` is 0 or `patch` exits 2, stop and report the scan JSON — the
build changed. Do not patch by hand.

### Linux (expected to work)

Geekbench ships a CLI tarball (`geekbench_x86_64` / `geekbench_aarch64`).

```bash
gblens --json scan ./geekbench_x86_64
gblens --json patch --binary ./geekbench_x86_64 --host 127.0.0.1:8080
# expect: host_hits>=1, scheme_hits>=1, signed=null (ELF is not code-signed)
```

If `scheme_hits == 0`, re-run with `--keep-https` and tell the user a trusted
local CA is required; or report the gap.

### Windows (community path, unverified)

```powershell
gblens --json scan "C:\Program Files\Geekbench 7\Geekbench 7.exe"
gblens --json patch --binary "C:\Program Files\Geekbench 7\Geekbench 7.exe" --host 127.0.0.1:8080
```

If the shortcut launches a per-user copy, find it first (`Get-ChildItem
$env:LOCALAPPDATA -Recurse -Filter "Geekbench*.exe"`) and patch that one.
Report `scan` output if anything is unexpected — that is a useful contribution.

## Step 2 — start the local endpoint

```bash
gblens serve --results ./results --http-port 8080 --open &
sleep 1
gblens --json doctor        # assert probe == 200
```

`--open` opens each rendered page as it arrives. Keep the process alive for the
whole benchmark.

## Step 3 — run the benchmark

- **macOS GUI**: `open "$HOME/Applications/Geekbench 7 Local.app"`, dismiss the
  welcome dialog, click **Run CPU Benchmark**. A real mouse click is required;
  `AXPress` is accepted but does nothing. Wait ~4 minutes.
- **CLI (all platforms)**: `./geekbench_x86_64 --cpu` (or the macOS copy's
  `Contents/Resources/geekbench_aarch64`).

The client will still finish with `Unable to parse server response` — that is
expected and harmless: the upload already landed. Do not try to fix it by
retrying the run.

## Step 4 — collect the result

```bash
ls -t results/*.document.json | head -1
gblens --json view "$(ls -t results/*.document.json | head -1)"
```

Assert `single.score > 0` and `multi.score > 0`. The rendered HTML is at
`results/<id>.html`; open it for the user.

## Step 5 — report

Give the user:

| Field | Value |
| --- | --- |
| Platform / build | e.g. macOS 26, Geekbench 7.1.0 |
| Single-Core | number |
| Multi-Core | number |
| Strongest 3 workloads | names + scores |
| Weakest 3 workloads | names + scores |
| Artifacts | `results/<id>.html`, `<id>.document.json` |
| Upload destination | `127.0.0.1:8080` only (state it explicitly) |

## Failure table

| Symptom | Meaning | Action |
| --- | --- | --- |
| `scan.patchable == false` | string table changed | stop, report scan JSON |
| `patch` exit 2 | instruction pattern changed | stop; suggest `--keep-https` + trusted CA |
| `Address already in use` | stale server | `lsof -i :8080`, kill, retry |
| no POST in `server.log` | app not patched / wrong copy | re-run `scan` on the copy's executable |
| `Unable to display benchmark results` | expected client-side validation failure | ignore, use the HTML |
| `security add-trusted-cert` returns 0 but no trust | TCC blocks headless sessions | do not loop; stay on HTTP |
| benchmark cancelled immediately (macOS) | embedded runner was re-signed | re-clone and patch again, patch only `Contents/MacOS/*` |

## Definition of done

- `results/<id>.document.json` exists, parses, has both scores
- `results/<id>.html` renders in a browser without network access
- `server.log` shows a POST to `127.0.0.1` and nothing outbound
- the user was told where the files are and that nothing was uploaded
