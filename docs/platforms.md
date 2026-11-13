# Platforms

The project is split so that only one layer is OS-specific:

```
render.py   pure Python, portable          → any Geekbench result file
server.py   pure Python, portable          → any platform with sockets
patch.py    byte-level edits, portable     → Mach-O / ELF / PE
            signing step, OS-specific      → codesign (macOS) / none (ELF, PE)
```

`gblens scan <binary>` tells you whether a given build is patchable before you
change anything. Run it on every new release.

## macOS — verified

| | |
| --- | --- |
| Build | `Geekbench 7.app` (universal: arm64 + x86_64) |
| Upload host | `browser.geekbench.com`, 2 occurrences (one per slice) |
| Scheme switch | `movk x?, #0x3a73, lsl #32` + conditional branch, 1 occurrence |
| Signing | required, `codesign --force --deep --sign - --options linker-signed` |
| Result window | web view of the browser page → breaks when the upload is blocked |

```bash
gblens scan "/Applications/Geekbench 7.app/Contents/MacOS/Geekbench 7"
# {"format":"macho-fat","host_hits":2,"scheme_hits":1,"patchable":true}
gblens patch --app "/Applications/Geekbench 7.app" --out ~/Applications/GB7-local.app
```

Two macOS traps (both handled):

- the embedded runner `Contents/Resources/geekbench_aarch64` must keep its
  original signature — re-signing it makes the GUI cancel every run
  (`Run completed without associated document`);
- `SUFeedURL` must not be *removed*, only redirected, or NSDocument breaks.

## Linux — expected to work, not yet verified here

Geekbench 7 ships a CLI-only tarball (`geekbench_x86_64`, `geekbench_aarch64`).
It has the same "requires internet, uploads automatically" behaviour and the
same Pro-only `--no-upload`.

```bash
gblens scan ./geekbench_x86_64
gblens patch --binary ./geekbench_x86_64 --host 127.0.0.1:8080
gblens serve --results ./results --http-port 8080 &
./geekbench_x86_64 --cpu
```

Notes:

- ELF is not code-signed; the patch is a pure byte edit, no `codesign` step.
- Same C++ sources mean the `movk` sequence should appear identically, so the
  scheme patch (forcing http) should apply. If `scheme_hits == 0`, run with
  `--keep-https` and give the client a CA it trusts — or simply file an issue
  with the `scan` output.
- No result-window problem on Linux: the CLI has no web view, so the upload is
  only used to print the summary and a URL.

## Windows — designed for, not yet verified

Windows builds are GUI (`Geekbench 7.exe`) plus an optional CLI. The string
table contains the same host; PE has no loader-time signature check, so the
patch itself is trivial:

```powershell
gblens scan "C:\Program Files\Geekbench 7\Geekbench 7.exe"
gblens patch --binary "C:\Program Files\Geekbench 7\Geekbench 7.exe" --host 127.0.0.1:8080
gblens serve --results .\results --http-port 8080
```

Open questions a Windows contributor should answer with a `scan` dump:

1. Does the PE contain `browser.geekbench.com` once or in every resource blob?
2. Is there Authenticode verification at launch (usually not, but check)?
3. Does the GUI shell out to the browser for the result page, or embed a
   WebView2? If WebView2, `http://127.0.0.1:8080/view/<id>` should load fine.
4. Does the installer drop a per-user copy under `%LOCALAPPDATA%`? Patch the
   copy the shortcut actually launches.

The renderer and server need no changes on Windows; `gblens serve` already
binds loopback only.

## Adding a platform

1. `gblens scan` the target binary, paste the JSON into an issue.
2. If `host_hits > 0`, `patch --binary` already works.
3. If the scheme switch moved, add a signature to `patch.py`
   (`MOVK_S_PATTERN` belongs to the current upstream codegen) or use
   `--keep-https` with a trusted CA.
4. Signing: implement a `resign()` branch for your platform, return `None`
   when the platform does not verify code.

## Status matrix

| Platform | Render | Serve | Patch (host) | Patch (scheme) | Sign | Verified |
| --- | --- | --- | --- | --- | --- | --- |
| macOS 26 | ✅ | ✅ | ✅ | ✅ | ✅ codesign | ✅ 7.1.0 |
| Linux | ✅ | ✅ | ✅ | ✅ expected | n/a | ⏳ |
| Windows | ✅ | ✅ | ✅ expected | ⏳ | n/a | ⏳ |
