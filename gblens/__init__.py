"""geekbench-local-lens — run Geekbench against a local endpoint.

Public API:
    gblens.render.parse_document(root) -> Report
    gblens.render.to_terminal(report) -> str
    gblens.render.to_html(report, title) -> str
    gblens.server.serve(args)
    gblens.patch.make_local_copy(app, out, host, force_http) -> PatchResult
"""
__version__ = "0.1.0"
