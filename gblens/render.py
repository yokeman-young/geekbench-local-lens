"""Render Geekbench result documents into terminal tables and standalone HTML.

The renderer is deliberately schema-tolerant: Geekbench 6 and 7 result files
you can obtain from the browser (``*.gb6`` / ``*.gb7``) differ in subtle ways,
and uploaded documents differ again.  Instead of hard-coding one shape we walk
the JSON tree and pick up anything that looks like a scored section.
"""
from __future__ import annotations

import html as htmllib
import json
import re
from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------
# schema sniffing
# --------------------------------------------------------------------------

def _norm(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _walk(node: Any, path: tuple[str, ...] = ()):
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from _walk(value, path + (str(key),))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, path + (str(index),))


NAME_KEYS = ("name", "workload", "metric", "test", "title", "label")
SCORE_KEYS = ("score", "value", "result")
RATE_KEYS = ("rate", "ratestring", "throughput", "unit", "units")


def _pick(node: dict, keys: tuple[str, ...], want_number: bool = False):
    for key, value in node.items():
        if _norm(key) in keys and (_is_number(value) if want_number else isinstance(value, str)):
            return value
    return None


def _workloads(node: dict) -> list[dict]:
    for key, value in node.items():
        if _norm(key) in ("workloads", "metrics", "tests", "benchmarks", "items") and isinstance(value, list):
            out = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                name = _pick(item, NAME_KEYS)
                score = _pick(item, SCORE_KEYS, want_number=True)
                rate = _pick(item, RATE_KEYS) or ""
                if name:
                    out.append({"name": name, "score": score, "rate": str(rate)})
            if out:
                return out
    return []


@dataclass
class Report:
    single: dict = field(default_factory=dict)
    multi: dict = field(default_factory=dict)
    info: dict = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.single and not self.multi


def _classify(name: str) -> str | None:
    key = _norm(name)
    if "single" in key:
        return "single"
    if "multi" in key:
        return "multi"
    return None


def _add(group: dict, name: str, section: dict, inherited: Any = None) -> None:
    target = group.setdefault("single" if _classify(name) == "single" else "multi",
                              {"name": name, "score": None, "workloads": []})
    if target["score"] is None:
        score = _pick(section, ("score", "scorevalue", "totalscore", "value"), want_number=True)
        target["score"] = score if score is not None else inherited
    target["workloads"].extend(_workloads(section))


def parse_document(root: dict) -> Report:
    """Turn an arbitrary Geekbench JSON document into a normalised Report."""
    groups: dict = {}

    def add(name: str, section: dict, inherited=None) -> None:
        kind = _classify(name)
        if not kind:
            return
        target = groups.setdefault(kind, {"name": name, "score": None, "workloads": []})
        if target["score"] is None:
            score = _pick(section, ("score", "scorevalue", "totalscore", "value"), want_number=True)
            target["score"] = score if score is not None else inherited
        target["workloads"].extend(_workloads(section))

    def absorb(node: dict) -> None:
        for key, value in node.items():
            if _norm(key) not in ("sections", "results", "groups", "phases", "benchmarks"):
                continue
            if not isinstance(value, list):
                continue
            for section in value:
                if not isinstance(section, dict):
                    continue
                name = _pick(section, NAME_KEYS) or ""
                if name and _classify(name):
                    add(name, section)

    if isinstance(root, dict):
        absorb(root)

    for path, node in _walk(root):
        if not path or not isinstance(node, dict):
            continue
        if _classify(path[-1]):
            add(path[-1], node)
        absorb(node)

    report = Report()
    report.single = groups.get("single", {})
    report.multi = groups.get("multi", {})
    report.info = _sysinfo(root)
    return report


def _sysinfo(root: dict) -> dict:
    flat: dict = {}
    for path, node in _walk(root):
        if not path:
            continue
        flat.setdefault(_norm(path[-1]), (node, path))

    wanted = {
        "os": ("operatingsystem", "os", "platform"),
        "model": ("model", "modelname", "devicemodel"),
        "cpu": ("cpu", "processorname", "chip"),
        "cores": ("cores", "corecount", "physicalcores", "threads"),
        "memory": ("memory", "ram", "physicalmemory", "memorysize"),
        "version": ("version", "geekbenchversion"),
        "date": ("date", "timestamp", "createdat", "uploaddate"),
    }
    info: dict = {}
    for field_name, candidates in wanted.items():
        for candidate in candidates:
            if candidate in flat:
                value, path = flat[candidate]
                if isinstance(value, (str, int, float)) and not isinstance(value, bool) and len(path) <= 4:
                    info[field_name] = value
                    break
    if info.get("model") and info.get("cpu") and str(info["model"]).lower() == str(info["cpu"]).lower():
        info.pop("cpu", None)
    return info


# --------------------------------------------------------------------------
# terminal output
# --------------------------------------------------------------------------

def fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value:,}" if isinstance(value, int) else str(value)


def to_terminal(report: Report) -> str:
    lines: list[str] = []
    for key in ("os", "model", "cpu", "cores", "memory", "version", "date"):
        if key in report.info:
            lines.append(f"{key:>8}: {report.info[key]}")
    if lines:
        lines.append("")

    groups = [g for g in ("single", "multi") if getattr(report, g)]
    if not groups:
        return "\n".join(lines + ["未识别到单核/多核分组，试试 --json 查看原始结构。"])

    lines.append(f"{'':<26}" + "".join(f"{g.upper():>12}" for g in groups))
    lines.append(f"{'Score':<26}" + "".join(f"{fmt(getattr(report, g)['score']):>12}" for g in groups))
    names: list[str] = []
    for g in groups:
        for w in getattr(report, g)["workloads"]:
            if w["name"] not in names:
                names.append(w["name"])
    for name in names:
        row = []
        for g in groups:
            w = next((x for x in getattr(report, g)["workloads"] if x["name"] == name), None)
            row.append(fmt(w["score"]) if w else "")
        lines.append(f"{name:<26}" + "".join(f"{c:>12}" for c in row))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# html output
# --------------------------------------------------------------------------

CSS = """
:root{color-scheme:light dark;--fg:#1c1c1e;--bg:#fff;--muted:#6b6b70;--line:#e5e5ea;--bar:#34c759;--bar-bg:#f2f2f7}
@media (prefers-color-scheme:dark){:root{--fg:#f2f2f7;--bg:#1c1c1e;--muted:#9a9aa0;--line:#2c2c2e;--bar:#30d158;--bar-bg:#2c2c2e}}
*{box-sizing:border-box}
body{margin:0;padding:48px 24px;font:15px/1.5 -apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",Arial,sans-serif;color:var(--fg);background:var(--bg)}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:22px;font-weight:600;margin:0 0 4px}
.sub{color:var(--muted);font-size:13px;margin:0 0 32px}
.scores{display:flex;gap:16px;margin-bottom:32px;flex-wrap:wrap}
.card{flex:1 1 200px;border:1px solid var(--line);border-radius:12px;padding:20px}
.card .label{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.card .value{font-size:40px;font-weight:600;line-height:1.1;margin-top:6px;font-variant-numeric:tabular-nums}
h2{font-size:15px;font-weight:600;margin:32px 0 12px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
td{padding:7px 0;border-bottom:1px solid var(--line);vertical-align:middle}
td.name{width:38%}
td.bar{width:42%;padding-right:16px}
td.score{text-align:right;width:72px;font-weight:500;padding-right:12px}
td.rate{text-align:right;width:150px;color:var(--muted);font-size:13px;white-space:nowrap}
.b{height:8px;border-radius:4px;background:var(--bar);min-width:2px}
.track{background:var(--bar-bg);border-radius:4px;overflow:hidden}
.sysinfo td:first-child{color:var(--muted);width:38%}
.sysinfo td:last-child{text-align:right}
footer{margin-top:40px;color:var(--muted);font-size:12px}
"""

LABELS = {"model": "Model", "cpu": "Processor", "cores": "Topology",
          "memory": "Memory", "os": "Operating System", "version": "Geekbench"}


def to_html(report: Report, title: str) -> str:
    esc = htmllib.escape
    parts = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>{esc(title)} — Geekbench</title><style>{CSS}</style></head><body><div class=\"wrap\">",
        f"<h1>{esc(title)}</h1>",
    ]
    meta = " · ".join(esc(str(report.info[k])) for k in ("version", "os", "date") if k in report.info)
    if meta:
        parts.append(f'<p class="sub">{meta}</p>')

    groups = [g for g in ("single", "multi") if getattr(report, g)]
    if groups:
        parts.append('<div class="scores">')
        for g in groups:
            label = "Single-Core" if g == "single" else "Multi-Core"
            parts.append(
                f'<div class="card"><div class="label">{label} Score</div>'
                f'<div class="value">{fmt(getattr(report, g)["score"])}</div></div>'
            )
        parts.append("</div>")

    rows = [(LABELS[k], report.info[k]) for k in ("model", "cpu", "cores", "memory", "os", "version")
            if k in report.info]
    if rows:
        parts.append('<h2>System Information</h2><table class="sysinfo">')
        for key, value in rows:
            parts.append(f"<tr><td>{esc(key)}</td><td>{esc(str(value))}</td></tr>")
        parts.append("</table>")

    for g in groups:
        section = getattr(report, g)
        parts.append(f'<h2>{esc(section["name"])} — {fmt(section["score"])}</h2><table>')
        workloads = [w for w in section["workloads"] if w.get("score") is not None]
        peak = max([w["score"] for w in workloads], default=0) or 1
        for w in workloads:
            width = max(2, round(100 * w["score"] / peak))
            parts.append(
                f'<tr><td class="name">{esc(w["name"])}</td>'
                f'<td class="bar"><div class="track"><div class="b" style="width:{width}%"></div></div></td>'
                f'<td class="score">{fmt(w["score"])}</td>'
                f'<td class="rate">{esc(w.get("rate") or "")}</td></tr>'
            )
        parts.append("</table>")

    parts.append("<footer>Rendered locally by geekbench-local-lens · never uploaded</footer></div></body></html>")
    return "\n".join(parts)


# --------------------------------------------------------------------------
# convenience
# --------------------------------------------------------------------------

def render_file(path: str) -> tuple[Report, str]:
    with open(path, encoding="utf-8", errors="replace") as handle:
        raw = handle.read().lstrip()
    root = json.loads(raw)
    report = parse_document(root)
    title = str(report.info.get("model") or report.info.get("cpu") or path.rsplit("/", 1)[-1])
    return report, to_html(report, title)
