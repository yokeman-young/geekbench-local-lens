"""Command line entry point: ``gblens``.

Designed to be driven by humans *and* agents:

* every subcommand accepts ``--json`` and prints exactly one JSON document
* exit codes are stable (0 ok, 1 usage/verification failure, 2 unsupported build)
* nothing prompts interactively
* ``gblens doctor`` reports environment facts as JSON
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from . import patch, render, scrub, server

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_UNSUPPORTED = 2


def _emit(payload: dict, as_json: bool, human: str = "") -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif human:
        print(human)


def cmd_serve(args: argparse.Namespace) -> int:
    server.serve(args)
    return EXIT_OK


def cmd_view(args: argparse.Namespace) -> int:
    report, page = render.render_file(args.file)
    out = args.html or os.path.splitext(args.file)[0] + ".html"
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(page)

    payload = {
        "file": os.path.abspath(args.file),
        "html": os.path.abspath(out),
        "info": report.info,
        "single": report.single or None,
        "multi": report.multi or None,
    }
    _emit(payload, args.json, render.to_terminal(report) + f"\n\nHTML -> {out}")
    if args.open:
        subprocess.run(["open", out])
    return EXIT_OK if not report.empty else EXIT_FAIL


def cmd_scan(args: argparse.Namespace) -> int:
    facts = patch.scan(args.binary)
    _emit(facts, args.json, json.dumps(facts, indent=2, ensure_ascii=False))
    return EXIT_OK if facts["patchable"] else EXIT_UNSUPPORTED


def cmd_patch(args: argparse.Namespace) -> int:
    try:
        if args.binary:
            result = patch.patch_binary(args.binary, host=args.host,
                                        force_http=not args.keep_https)
            out = args.binary
            next_steps = ["gblens serve --results ./results", f"run {args.binary}"]
        else:
            result = patch.make_local_copy(args.app, args.out, host=args.host,
                                           force_http=not args.keep_https)
            out = args.out
            next_steps = ["gblens serve --results ./results", f'open "{args.out}"']
    except SystemExit as exc:
        _emit({"ok": False, "error": str(exc)}, args.json, str(exc))
        return EXIT_UNSUPPORTED

    payload = {
        "ok": bool(result),
        "output": out,
        "format": result.format,
        "host": args.host,
        "host_hits": result.host_hits,
        "scheme_hits": result.scheme_hits,
        "signed": result.signed,
        "next": next_steps,
    }
    human = (f"patched {out}\n"
             f"  host hits : {result.host_hits}\n"
             f"  scheme    : {result.scheme_hits} (http forced)\n"
             f"  signed    : {result.signed}")
    _emit(payload, args.json, human)
    return EXIT_OK if result.signed else EXIT_FAIL


def _bundle_executable(app: str) -> str:
    plist = os.path.join(app, "Contents", "Info.plist")
    name = subprocess.run(["/usr/libexec/PlistBuddy", "-c", "Print CFBundleExecutable", plist],
                          capture_output=True, text=True).stdout.strip()
    return os.path.join(app, "Contents", "MacOS", name or "")


def cmd_info(args: argparse.Namespace) -> int:
    plist = os.path.join(args.app, "Contents", "Info.plist")
    facts = {}
    for key in ("CFBundleIdentifier", "CFBundleShortVersionString", "CFBundleExecutable"):
        facts[key] = subprocess.run(["/usr/libexec/PlistBuddy", "-c", f"Print {key}", plist],
                                    capture_output=True, text=True).stdout.strip()
    _emit(facts, args.json, "\n".join(f"{k}: {v}" for k, v in facts.items()))
    return EXIT_OK


def cmd_scrub(args: argparse.Namespace) -> int:
    with open(args.file, encoding="utf-8") as handle:
        original = json.load(handle)
    cleaned = scrub.scrub(original, level=args.level)
    out = args.out or os.path.splitext(args.file)[0] + f".scrubbed.json"
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(cleaned, handle, ensure_ascii=False, indent=2)
    payload = {"input": os.path.abspath(args.file), "output": os.path.abspath(out),
               "level": args.level, **scrub.summarise(original, cleaned)}
    _emit(payload, args.json, f"scrubbed -> {out}\n{json.dumps(payload, indent=2)}")
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    facts = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "app": args.app,
        "app_exists": os.path.isdir(args.app),
        "app_version": None,
        "probe": None,
        "results_dir": os.path.abspath(args.results),
        "results_count": 0,
    }
    if facts["app_exists"]:
        plist = os.path.join(args.app, "Contents", "Info.plist")
        facts["app_version"] = subprocess.run(
            ["/usr/libexec/PlistBuddy", "-c", "Print CFBundleShortVersionString", plist],
            capture_output=True, text=True).stdout.strip()

    try:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{args.http_port}/", timeout=2) as response:
            facts["probe"] = response.status
    except Exception as exc:  # noqa: BLE001
        facts["probe"] = f"unreachable: {exc}"

    if os.path.isdir(args.results):
        facts["results_count"] = sum(1 for n in os.listdir(args.results) if n.endswith(".html"))

    _emit(facts, args.json, json.dumps(facts, indent=2, ensure_ascii=False))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gblens",
        description="Run Geekbench locally: fake upload endpoint, local rendering, binary patching.")
    parser.add_argument("--json", action="store_true", help="machine readable output (one JSON document)")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=False,
                        help="machine readable output (one JSON document)")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", parents=[common], help="start the local upload endpoint")
    serve.add_argument("--results", default="./results")
    serve.add_argument("--http-port", type=int, default=server.DEFAULT_HTTP_PORT,
                       help="plain HTTP port (0 disables)")
    serve.add_argument("--https-port", type=int, default=0, help="HTTPS port (needs --cert/--key)")
    serve.add_argument("--cert")
    serve.add_argument("--key")
    serve.add_argument("--open", action="store_true", help="open each rendered page")
    serve.set_defaults(func=cmd_serve)

    view = sub.add_parser("view", parents=[common], help="render a .gb6/.gb7/.json result file")
    view.add_argument("file")
    view.add_argument("--html")
    view.add_argument("--open", action="store_true")
    view.set_defaults(func=cmd_view)

    patcher = sub.add_parser("patch", parents=[common], help="clone an app and point it at localhost")
    patcher.add_argument("--app", default="/Applications/Geekbench 7.app",
                         help="macOS app bundle to clone (ignored with --binary)")
    patcher.add_argument("--binary", help="patch a single executable in place (Linux/Windows CLI builds)")
    patcher.add_argument("--out", default=os.path.expanduser("~/Applications/Geekbench 7 Local.app"))
    patcher.add_argument("--host", default="127.0.0.1:8080")
    patcher.add_argument("--keep-https", action="store_true")
    patcher.set_defaults(func=cmd_patch)

    scanner = sub.add_parser("scan", parents=[common], help="inspect a binary: format, host/scheme match")
    scanner.add_argument("binary")
    scanner.set_defaults(func=cmd_scan)

    scrubber = sub.add_parser("scrub", parents=[common], help="remove identifying fields from a result file")
    scrubber.add_argument("file")
    scrubber.add_argument("--level", choices=("light", "strict"), default="strict")
    scrubber.add_argument("--out")
    scrubber.set_defaults(func=cmd_scrub)

    info = sub.add_parser("info", parents=[common], help="bundle facts for an app")
    info.add_argument("--app", default="/Applications/Geekbench 7.app")
    info.set_defaults(func=cmd_info)

    doctor = sub.add_parser("doctor", parents=[common], help="environment self-check")
    doctor.add_argument("--app", default="/Applications/Geekbench 7.app")
    doctor.add_argument("--results", default="./results")
    doctor.add_argument("--http-port", type=int, default=server.DEFAULT_HTTP_PORT)
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "json"):
        args.json = False
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
