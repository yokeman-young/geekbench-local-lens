"""A fake Geekbench Browser endpoint bound to localhost.

Point the client at ``http://127.0.0.1:<port>`` (see :mod:`gblens.patch`) and
every upload lands in ``results/`` instead of Primate Labs' servers.  The raw
multipart body, the extracted ``document`` JSON and a rendered HTML page are
all written out; nothing leaves the machine.

Why this exists: the free Geekbench build refuses to run offline and its result
window is a web view of the browser page.  Intercepting the upload makes the
benchmark local while keeping the normal client workflow.
"""
from __future__ import annotations

import argparse
import datetime
import http.server
import json
import os
import re
import ssl
import subprocess
import threading
import urllib.parse

from . import render


DEFAULT_HTTP_PORT = 8080
DEFAULT_HTTPS_PORT = 8443


class Store:
    def __init__(self, directory: str, auto_open: bool = False) -> None:
        self.directory = directory
        self.auto_open = auto_open
        os.makedirs(self.directory, exist_ok=True)

    def save(self, body: bytes) -> dict:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        raw_path = os.path.join(self.directory, f"{stamp}.json")
        with open(raw_path, "wb") as handle:
            handle.write(body)

        meta: dict = {"id": stamp, "raw": raw_path, "document": None, "html": None}
        try:
            text = body.decode("utf-8", "replace")
            match = re.search(r'name="document"\s*\r?\n\r?\n(.*?)\r?\n--', text, re.S)
            if match:
                document = json.loads(match.group(1))
                doc_path = os.path.join(self.directory, f"{stamp}.document.json")
                with open(doc_path, "w", encoding="utf-8") as handle:
                    json.dump(document, handle, ensure_ascii=False, indent=2)
                meta["document"] = doc_path

                report = render.parse_document(document)
                if not report.empty:
                    title = str(report.metrics.get("Model")
                                or report.info.get("model")
                                or report.info.get("cpu")
                                or stamp)
                    html_path = os.path.join(self.directory, f"{stamp}.html")
                    with open(html_path, "w", encoding="utf-8") as handle:
                        handle.write(render.to_html(report, title))
                    meta["html"] = html_path
                    if self.auto_open:
                        subprocess.Popen(["open", html_path])
        except Exception as exc:  # noqa: BLE001 - a bad upload must not kill the server
            meta["error"] = str(exc)
        return meta

    def listing(self) -> list[tuple[str, str]]:
        items = []
        for name in sorted(os.listdir(self.directory)):
            if name.endswith(".html"):
                items.append((name[:-5], name))
        return items


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    store: Store
    scheme = "http"
    port = DEFAULT_HTTP_PORT
    log_path: str | None = None

    # ---------------------------------------------------------------- utils
    def _log(self, message: str) -> None:
        line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {message}"
        print(line, flush=True)
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def _send(self, code: int, body, ctype: str = "application/json") -> None:
        payload = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:  # noqa: D102 - quieter access log
        self._log(f"{self.command} {self.path}")

    # ---------------------------------------------------------------- verbs
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        meta = self.store.save(body)
        self._log(f"POST {self.path} len={len(body)} -> {os.path.basename(meta['raw'])}"
                  + (f" rendered {os.path.basename(meta['html'])}" if meta["html"] else ""))
        # The desktop client expects a small JSON blob with a result URL.  We do
        # not know every field it insists on, so send a superset; the important
        # part for the local workflow is that the upload itself succeeded.
        base = f"{self.scheme}://127.0.0.1:{self.port}"
        result = {
            "id": meta["id"],
            "result_id": meta["id"],
            "status": 0,
            "code": 0,
            "url": f"{base}/view/{meta['id']}",
            "view_url": f"{base}/view/{meta['id']}",
            "claim_url": f"{base}/claim/{meta['id']}",
        }
        self._send(200, json.dumps(result))

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "view":
            page = os.path.join(self.store.directory, f"{parts[1]}.html")
            if os.path.exists(page):
                with open(page, encoding="utf-8") as handle:
                    self._send(200, handle.read(), "text/html; charset=utf-8")
                return
            self._send(404, "<h1>unknown result</h1>", "text/html; charset=utf-8")
        elif len(parts) == 2 and parts[0] == "claim":
            self._send(200, "<h1>local claim</h1>", "text/html; charset=utf-8")
        elif parsed.path in ("/", "/index.html"):
            items = "".join(f'<li><a href="/view/{rid}">{rid}</a></li>' for rid, _ in self.store.listing())
            self._send(200, f"<h1>Local Geekbench results</h1><ul>{items}</ul>", "text/html; charset=utf-8")
        else:
            # The client may open https://host/v7/cpu/<id>-style URLs; fall back
            # to the most recent rendered page.
            items = self.store.listing()
            if items:
                page = os.path.join(self.store.directory, items[-1][1])
                with open(page, encoding="utf-8") as handle:
                    self._send(200, handle.read(), "text/html; charset=utf-8")
            else:
                self._send(404, "<h1>no results yet</h1>", "text/html; charset=utf-8")

    def do_HEAD(self) -> None:
        self._send(200, "")


def make_server(store: Store, port: int, use_tls: bool = False,
                cert: str | None = None, key: str | None = None):
    handler = type("BoundHandler", (Handler,), {
        "store": store,
        "scheme": "https" if use_tls else "http",
        "port": port,
        "log_path": os.path.join(store.directory, "..", "server.log"),
    })
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    if use_tls:
        if not (cert and key):
            raise SystemExit("TLS needs --cert and --key")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


def serve(args: argparse.Namespace) -> None:
    store = Store(args.results, auto_open=args.open)
    servers = []
    threads = []

    if args.http_port:
        http_server = make_server(store, args.http_port, use_tls=False)
        servers.append(http_server)
        threads.append(threading.Thread(target=http_server.serve_forever, daemon=True))
    if args.https_port and args.cert and args.key:
        https_server = make_server(store, args.https_port, use_tls=True,
                                   cert=args.cert, key=args.key)
        servers.append(https_server)
        threads.append(threading.Thread(target=https_server.serve_forever, daemon=True))

    if not servers:
        raise SystemExit("nothing to serve: pass --http-port and/or --https-port with certs")

    for thread in threads:
        thread.start()
    ports = ", ".join(f"{s.server_address[1]}" for s in servers)
    print(f"listening on 127.0.0.1 ({ports}); results -> {os.path.abspath(args.results)}", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        for server in servers:
            server.shutdown()
