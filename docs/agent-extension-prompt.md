# Prompt template: port gblens to another platform

Copy this into an agent session (Claude Code, Codex, DeepSeek Harness, …) with
the target binary available on disk.

---

You are extending the open-source project `geekbench-local-lens` (Python 3.9+,
no third-party deps) to a new platform. Work only inside the repo and a scratch
directory; never modify an installed application.

Goal: make `gblens scan` / `gblens patch --binary` work for the target build,
and confirm the local upload workflow end to end.

Step 1 — reconnaissance (no edits)
1. `gblens --json scan <TARGET_BINARY>` and paste the JSON.
2. Report `format`, `host_hits`, `scheme_hits`, `size`.
3. If `host_hits == 0`, run:
   `strings -a -t d <binary> | grep -i geekbench | head -30`
   and report candidate host strings and their byte offsets.

Step 2 — decide the edit
- `host_hits > 0` → the portable host swap applies; no new code needed.
- `scheme_hits == 0` → disassemble the function that references the host string
  (e.g. `llvm-objdump -d --no-show-raw-insn` on the slice/section containing it)
  and locate the http/https selection. Propose a 4-byte instruction pattern and
  the relative offset of the branch to flip. Do not hardcode absolute offsets.
- If the platform verifies code signatures, implement `resign()` for it in
  `gblens/platforms/<os>.py`; otherwise return `None`.

Step 3 — implement
- Add the smallest possible change to `gblens/patch.py` or a new module under
  `gblens/platforms/`.
- Keep public behaviour: `scan()` keys unchanged, `patch_binary()` signature
  unchanged, exit codes unchanged.

Step 4 — verify (must all pass)
1. `python -m unittest discover -s tests -v`
2. `gblens --json scan <patched binary>` → `host_hits` reflects the new host
   (the old pattern should now be 0).
3. `gblens serve --results /tmp/gblens --http-port 8080 &`
4. run the benchmark, then `gblens --json view /tmp/gblens/*.document.json`
   → `single.score` and `multi.score` are non-null.

Step 5 — report
Output a table: platform, format, host_hits, scheme_hits, signing, verified yes/no,
plus any byte pattern you added and why it is stable across releases.

Rules: no Pro licence bypass, no uploading to remote hosts, no editing the
installed app in place, stop and ask if `scan.patchable == false`.
