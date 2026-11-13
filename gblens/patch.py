"""Portable binary patching for Geekbench builds.

The two interesting edits are **format-agnostic byte operations**:

1. ``browser.geekbench.com`` lives in the read-only string table of every
   Geekbench build (Mach-O, ELF and PE alike). Because it is exactly 21 bytes,
   replacing it with a shorter host plus NUL padding never shifts a section and
   never needs a format-aware rewrite.

2. The URL builder's http/https switch is compiled from the same C++ source on
   every platform, so the ``movk x?, #0x3a73, lsl #32`` that spells the ``s:``
   in ``https://`` followed by a conditional branch appears identically. We look
   for that instruction and turn the branch into an unconditional one.

Only the *signing* step is platform specific: macOS needs an ad-hoc ``codesign``
after modifying the Mach-O code segment; ELF and PE builds are typically not
verified on load, so the patch is a no-op there (`signed: null`).
"""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
from dataclasses import dataclass, field


HOST_OLD = b"browser.geekbench.com"
MOVK_S_PATTERN = struct.pack("<I", 0xF2C74E68)   # movk x?, #0x3a73, lsl #32
BNE = 0x54000121
BRANCH = 0x14000009

MACHO_MAGICS = {
    b"\xcf\xfa\xed\xfe": "macho",
    b"\xce\xfa\xed\xfe": "macho",
    b"\xfe\xed\xfa\xcf": "macho",
    b"\xfe\xed\xfa\xce": "macho",
    b"\xca\xfe\xba\xbe": "macho-fat",
    b"\xbe\xba\xfe\xca": "macho-fat",
}
ELF_MAGIC = b"\x7fELF"
PE_MAGIC = b"MZ"


def sniff_format(path: str) -> str:
    with open(path, "rb") as handle:
        head = handle.read(4)
    if head in MACHO_MAGICS:
        return MACHO_MAGICS[head]
    if head == ELF_MAGIC:
        return "elf"
    if head[:2] == PE_MAGIC:
        return "pe"
    return "unknown"


# --------------------------------------------------------------------------
# byte-level operations (format agnostic)
# --------------------------------------------------------------------------

def patch_host(path: str, new_host: str, old: bytes = HOST_OLD) -> int:
    """Replace every occurrence of ``old`` with ``new_host`` (NUL padded)."""
    payload = new_host.encode()
    if len(payload) > len(old):
        raise ValueError(f"replacement {new_host!r} is longer than {len(old)} bytes")
    padded = payload + b"\x00" * (len(old) - len(payload))

    with open(path, "rb") as handle:
        blob = bytearray(handle.read())

    count = start = 0
    while True:
        index = blob.find(old, start)
        if index < 0:
            break
        blob[index:index + len(old)] = padded
        count += 1
        start = index + len(old)

    if count:
        with open(path, "wb") as handle:
            handle.write(blob)
    return count


def patch_scheme(path: str) -> int:
    """Force the http branch of the URL builder.  Returns number of rewrites."""
    with open(path, "rb") as handle:
        blob = bytearray(handle.read())

    count = start = 0
    while True:
        index = blob.find(MOVK_S_PATTERN, start)
        if index < 0:
            break
        branch = index - 20
        if branch >= 0 and struct.unpack("<I", blob[branch:branch + 4])[0] == BNE:
            blob[branch:branch + 4] = struct.pack("<I", BRANCH)
            count += 1
        start = index + 1

    if count:
        with open(path, "wb") as handle:
            handle.write(blob)
    return count


def scan(path: str) -> dict:
    """Report what a build looks like and whether the patches would apply."""
    with open(path, "rb") as handle:
        blob = handle.read()
    return {
        "path": os.path.abspath(path),
        "format": sniff_format(path),
        "size": len(blob),
        "host_hits": blob.count(HOST_OLD),
        "host_variants": [h.decode() for h in (b"browser.geekbench.com", b"geekbench.com/browser") if h in blob],
        "scheme_hits": _count_scheme_patterns(blob),
        "patchable": blob.count(HOST_OLD) > 0,
    }


def _count_scheme_patterns(blob: bytes) -> int:
    count = start = 0
    while True:
        index = blob.find(MOVK_S_PATTERN, start)
        if index < 0:
            return count
        branch = index - 20
        if branch >= 0 and struct.unpack("<I", blob[branch:branch + 4])[0] == BNE:
            count += 1
        start = index + 1


# --------------------------------------------------------------------------
# signing (platform specific)
# --------------------------------------------------------------------------

def resign(path: str, deep: bool = False, linker_signed: bool = False) -> bool | None:
    """Re-sign ``path`` on macOS.  Returns None on platforms without code signing."""
    if not path.lower().endswith((".app", "/")):
        format_name = sniff_format(path)
    else:
        format_name = "macho"

    if format_name not in ("macho", "macho-fat") and not path.endswith(".app"):
        return None

    command = ["codesign", "--force", "--sign", "-"]
    if deep:
        command.append("--deep")
    if linker_signed:
        command += ["--options", "linker-signed"]
    command.append(path)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr.strip())
        return False
    return subprocess.run(["codesign", "-v", path], capture_output=True).returncode == 0


def info_plist_disable_updates(app: str) -> None:
    plist = os.path.join(app, "Contents", "Info.plist")
    if not os.path.exists(plist):
        return
    subprocess.run(["/usr/libexec/PlistBuddy", "-c",
                    "Set :SUFeedURL https://invalid.invalid/appcast", plist], capture_output=True)
    for key in ("SUEnableAutomaticChecks", "SUAutomaticallyUpdate"):
        subprocess.run(["/usr/libexec/PlistBuddy", "-c", f"Add :{key} bool false", plist], capture_output=True)
        subprocess.run(["/usr/libexec/PlistBuddy", "-c", f"Set :{key} false", plist], capture_output=True)


def clone_app(src: str, dst: str) -> None:
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    result = subprocess.run(["cp", "-cR", src, dst], capture_output=True)
    if result.returncode != 0:
        subprocess.run(["cp", "-R", src, dst], check=True)


# --------------------------------------------------------------------------
# high level helpers
# --------------------------------------------------------------------------

@dataclass
class PatchResult:
    host_hits: int = 0
    scheme_hits: int = 0
    signed: bool | None = None
    format: str = "unknown"
    output: str = ""

    def __bool__(self) -> bool:
        return self.host_hits > 0


def _bundle_executable(app: str) -> str:
    plist = os.path.join(app, "Contents", "Info.plist")
    name = subprocess.run(["/usr/libexec/PlistBuddy", "-c", "Print CFBundleExecutable", plist],
                          capture_output=True, text=True).stdout.strip() or "Geekbench 7"
    return os.path.join(app, "Contents", "MacOS", name)


def make_local_copy(app: str, out: str, host: str = "127.0.0.1:8080",
                    force_http: bool = True) -> PatchResult:
    """Clone a macOS ``.app`` and point it at ``host``."""
    clone_app(app, out)
    executable = _bundle_executable(out)
    result = patch_binary(executable, host=host, force_http=force_http, resign_after=False)
    info_plist_disable_updates(out)
    result.signed = resign(out, deep=True, linker_signed=force_http)
    result.output = out
    return result


def patch_binary(path: str, host: str = "127.0.0.1:8080", force_http: bool = True,
                 output: str | None = None, resign_after: bool = True) -> PatchResult:
    """Patch a single executable (Mach-O / ELF / PE) in place or into ``output``."""
    target = output or path
    result = PatchResult(output=target)
    result.format = sniff_format(path)
    result.host_hits = patch_host(path, host)
    if result.host_hits == 0:
        raise SystemExit(f"host string not found in {path}; unsupported build or already patched")
    if force_http:
        result.scheme_hits = patch_scheme(path)
    if resign_after:
        result.signed = resign(path, deep=False, linker_signed=force_http)
    return result


def patch_app(app: str, out: str, host: str = "127.0.0.1:8080",
              force_http: bool = True) -> PatchResult:
    """Clone an app bundle and patch its main executable."""
    clone_app(app, out)
    executable = _bundle_executable(out)
    result = PatchResult(output=out)
    result.format = sniff_format(executable)
    result.host_hits = patch_host(executable, host)
    if result.host_hits == 0:
        raise SystemExit(f"host string not found in {executable}; unsupported build or already patched")
    if force_http:
        result.scheme_hits = patch_scheme(executable)
    info_plist_disable_updates(out)
    result.signed = resign(out, deep=True, linker_signed=force_http)
    return result
