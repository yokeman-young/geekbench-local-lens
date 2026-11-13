# Extending to a new platform

The point of this repository is that adding a platform is a **bounded, testable**
job: one byte-pattern problem, one signing problem, zero renderer work.

```
render.py   ── reused as-is        (pure Python, any OS, any Geekbench version)
server.py   ── reused as-is        (loopback HTTP/HTTPS)
patch.py    ── 90% reused          (string swap + instruction pattern are portable)
             └─ signing hook       ← the only genuinely OS-specific piece
```

## What a port needs to answer

1. **Where is the host string?** Run `gblens scan <binary>`:
   - `host_hits > 0` → the portable host swap already works.
   - `format` tells you Mach-O / ELF / PE.
2. **Is the scheme switch still there?** `scheme_hits > 0` means the
   `movk x?, #0x3a73, lsl #32` + `b.ne` sequence survived codegen. If it is 0,
   you can still ship with `--keep-https` and a trusted CA, or locate the new
   comparison and add a pattern to `patch.py`.
3. **Does the platform verify code?** If yes, extend `resign()`; if no, return
   `None` and the patch is a pure byte edit.

## Adding a platform package (recommended shape)

```
gblens/patch.py            portable primitives (patch_host, patch_scheme, scan)
gblens/platforms/base.py   class Platform: detect(), resign(), launch_hint()
gblens/platforms/darwin.py codesign --deep --options linker-signed
gblens/platforms/linux.py  resign() -> None
gblens/platforms/windows.py  resign() -> None (Authenticode not enforced)
```

`Platform.detect(path)` returns the format string from `patch.sniff_format`;
`resign` returns `True/False/None`. Nothing else in the codebase needs to know.

## Test contract for a new platform

Any port must keep these green:

```bash
python -m unittest discover -s tests -v      # renderer + schema tests
gblens --json scan <binary>                  # patchable=true
gblens --json patch --binary <bin> --host 127.0.0.1:8080
gblens serve --results /tmp/gblens --http-port 8080 &
gblens --json view <a real result file>      # single/multi non-null
```

CI runs the renderer tests on `ubuntu-latest` and `macos-latest`; add your OS to
the matrix in `.github/workflows/ci.yml` when you land a port.

## Using an agent to do the port

`docs/agent-extension-prompt.md` contains a ready prompt. The short version:

> Run `gblens scan` on the target build, report `format/host_hits/scheme_hits`.
> If `host_hits == 0`, search the binary for `browser.geekbench.com` variants and
> report the nearest ASCII strings. If `scheme_hits == 0`, disassemble around
> references to the host string and find the scheme selection; propose a byte
> pattern. Never guess offsets: propose a `scan` → `patch` → `verify` loop.

## What is out of scope

- Unlocking Pro features (`--no-upload`, `--save`, `--json` in the client).
- Reimplementing the vendor's exact HTML — the rendered page is equivalent, not
  identical.
