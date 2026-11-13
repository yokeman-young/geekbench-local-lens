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


GPU_APIS = {1: "OpenCL", 2: "CUDA", 3: "Metal", 4: "Vulkan"}

WORKLOAD_UNITS = {
    "File Compression": ("MB/sec", 1e6),
    "Navigation": ("routes/sec", 1),
    "HTML5 Browser": ("pages/sec", 1),
    "PDF Viewer": ("Mpixels/sec", 1e6),
    "Photo Library": ("images/sec", 1),
    "Clang": ("Klines/sec", 1e3),
    "Text Processing": ("pages/sec", 1),
    "Asset Compression": ("MB/sec", 1e6),
    "HDR": ("Mpixels/sec", 1e6),
    "Photo Editor": ("images/sec", 1),
    "Ray Tracer": ("Ksamples/sec", 1e3),
    "Structure from Motion": ("Kpixels/sec", 1e3),
    "Game Physics": ("FPS", 1),
    "Video Encoder": ("FPS", 1),
    "Audio Encoder": ("Msamples/sec", 1e6),
    "Video Player": ("FPS", 1),
}

METRIC_LABELS = {
    1: "Platform", 2: "Compiler", 3: "Operating System", 4: "Model ID",
    5: "Model", 7: "Processor", 12: "Cores", 13: "Threads",
    14: "Processors", 15: "Base Frequency", 17: "L1 Instruction Cache",
    19: "L1 Data Cache", 21: "L2 Cache", 23: "L3 Cache", 25: "L4 Cache",
    29: "Memory", 34: "CPU", 45: "Clusters", 46: "Cluster 1",
    51: "Cluster 2", 89: "Peak Clock", 20000: "Instruction Sets",
}

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
                rate = next((item[x] for x in item
                             if _norm(x) == "rate" and _is_number(item[x])), "")
                if rate == "":
                    rate = _pick(item, RATE_KEYS) or ""
                runtime = next((item[x] for x in item
                                if _norm(x) == "runtime" and _is_number(item[x])), None)
                threads = next((item[x] for x in item
                                if _norm(x) == "threads" and _is_number(item[x])), None)
                runs = next((item[x] for x in item
                             if _norm(x) == "runtimes" and isinstance(item[x], list)), None)
                if name:
                    out.append({"name": name, "score": score,
                                "rate": rate if _is_number(rate) else str(rate),
                                "runtime": runtime, "threads": threads, "runs": runs})
            if out:
                return out
    return []


@dataclass
class Report:
    single: dict = field(default_factory=dict)
    multi: dict = field(default_factory=dict)
    gpu: dict = field(default_factory=dict)
    info: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    details: dict = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.single and not self.multi and not self.gpu


def _classify(name: str) -> str | None:
    key = _norm(name)
    if "single" in key:
        return "single"
    if "multi" in key:
        return "multi"
    if "gpu" in key or "compute" in key:
        return "gpu"
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
    report.gpu = groups.get("gpu", {})
    report.info = _sysinfo(root)
    report.metrics = collect_metrics(root)
    report.details = collect_details(root)
    return report


def collect_details(root: dict) -> dict:
    """Run options, frequency samples and run metadata (for the folded section)."""
    out: dict = {"options": {}, "meta": {}, "frequencies": []}
    if not isinstance(root, dict):
        return out
    if isinstance(root.get("options"), dict):
        out["options"] = root["options"]
    for key in ("version", "build", "date", "valid", "complete_benchmark", "branch"):
        if root.get(key) is not None:
            out["meta"][key] = root[key]
    for key in ("gpu_api", "gpu_platform_name", "gpu_device_name"):
        if root.get(key) not in (None, "", -1):
            out[key] = root[key]
    frequency = root.get("processor_frequency")
    if isinstance(frequency, dict):
        out["frequencies"] = [f for f in frequency.get("frequencies", []) if _is_number(f)]
    return out


def collect_metrics(root: dict) -> dict:
    """Map the document's numeric metric ids to readable labels."""
    out: dict = {}
    for _, node in _walk(root):
        if not isinstance(node, dict):
            continue
        entries = node.get("metrics")
        if not isinstance(entries, list):
            continue
        for item in entries:
            if not isinstance(item, dict):
                continue
            label = METRIC_LABELS.get(item.get("id"))
            value = item.get("value")
            if label and isinstance(value, str) and value.strip():
                out.setdefault(label, value.strip())
    return out


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


def rate_string(name: str, rate) -> str:
    """Browser-style description, e.g. ``456.5 MB/sec``."""
    if isinstance(rate, str):
        try:
            rate = float(rate)
        except ValueError:
            return rate
    if not _is_number(rate):
        return ""
    unit, scale = WORKLOAD_UNITS.get(name, ("", 1))
    if not unit:
        return ""
    value = rate / scale
    text = f"{value:.2f}" if value < 10 else f"{value:.1f}"
    return f"{text} {unit}"


def to_terminal(report: Report) -> str:
    lines: list[str] = []
    for key in ("os", "model", "cpu", "cores", "memory", "version", "date"):
        if key in report.info:
            lines.append(f"{key:>8}: {report.info[key]}")
    if lines:
        lines.append("")

    groups = [g for g in ("single", "multi", "gpu") if getattr(report, g)]
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
td.score{text-align:right;width:150px;font-weight:500;padding-right:16px;white-space:nowrap}
td.score .desc{display:block;font-weight:400;font-size:12px;color:var(--muted);margin-top:2px}
td.rate{text-align:right;width:150px;color:var(--muted);font-size:13px;white-space:nowrap}
.b{height:8px;border-radius:4px;background:var(--bar);min-width:2px}
.track{background:var(--bar-bg);border-radius:4px;overflow:hidden}
.sysinfo td:first-child{color:var(--muted);width:38%}
.sysinfo td:last-child{text-align:right}
footer{margin-top:40px;color:var(--muted);font-size:12px}
:root{--card:#fafafa;--card-hover:#f2f2f7}
@media (prefers-color-scheme:dark){:root{--card:#242426;--card-hover:#2c2c2e}}
details.tech{margin-top:44px;border-top:1px solid var(--line);padding-top:20px}
details.tech summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:10px;padding:14px 16px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--fg);font-size:14px;font-weight:600;transition:background .15s ease,border-color .15s ease}
details.tech summary::-webkit-details-marker{display:none}
details.tech summary::before{content:"▸";color:var(--muted);font-size:11px;transition:transform .2s ease}
details.tech[open] summary::before{transform:rotate(90deg)}
details.tech summary:hover{background:var(--card-hover);border-color:var(--muted)}
details.tech summary .hint{margin-left:auto;font-weight:400;font-size:12px;color:var(--muted)}
details.tech[open] summary{margin-bottom:8px}
details.tech h3{font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin:28px 0 10px}
svg.spark{display:block;width:100%;height:96px;border:1px solid var(--line);border-radius:10px;background:var(--bar-bg);background-image:linear-gradient(var(--line) 1px,transparent 1px);background-size:100% 24px}
svg.spark polyline{fill:none;stroke:var(--bar);stroke-width:1.5;vector-effect:non-scaling-stroke;stroke-linejoin:round;stroke-linecap:round}
table.timing{font-size:13px}
table.timing th{text-align:left;font-weight:500;color:var(--muted);padding:0 0 6px;border-bottom:1px solid var(--line);font-size:12px}
table.timing td{padding:7px 0;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums;width:36%}
table.timing tr.grp td{padding-top:18px;border-bottom:none;color:var(--muted);font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase}
table.timing td.num{width:80px}
td.iter{color:var(--muted);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
"""

LABELS = {"model": "Model", "cpu": "Processor", "cores": "Topology",
          "memory": "Memory", "os": "Operating System", "version": "Geekbench"}


def _details_block(report: Report, groups: list) -> str:
    esc = htmllib.escape
    details = report.details or {}
    parts = ['<details class="tech"><summary>Technical details · engineering data'
             '<span class="hint">click to expand</span></summary>']
    rows = list((details.get("meta") or {}).items()) + list((details.get("options") or {}).items())
    if rows:
        parts.append('<h3>Run</h3><table class="sysinfo">')
        for key, value in rows:
            parts.append(f'<tr><td>{esc(str(key))}</td><td>{esc(str(value))}</td></tr>')
        parts.append('</table>')

    freqs = details.get("frequencies") or []
    if freqs:
        lo, hi = min(freqs), max(freqs)
        avg = sum(freqs) / len(freqs)
        parts.append(f'<h3>CPU frequency · n={len(freqs)} · min {lo} / avg {avg:.0f} / max {hi} MHz</h3>')
        width, height = 760, 90
        span = (hi - lo) or 1
        step = width / max(1, len(freqs) - 1)
        points = " ".join(
            f"{i * step:.1f},{height - (value - lo) / span * (height - 8) - 4:.1f}"
            for i, value in enumerate(freqs))
        parts.append(f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
                     f'<polyline points="{points}"/></svg>')

    timing = []
    for kind in ("single", "multi", "gpu"):
        group = next((g for g in groups if g == kind), None)
        section = getattr(report, kind, None)
        if not section:
            continue
        timing.append(f'<tr class="grp"><td colspan="4">{esc(section["name"])} · {fmt(section["score"])}</td></tr>')
        for workload in section["workloads"]:
            runtime = workload.get("runtime")
            runs = workload.get("runs") or []
            timing.append(
                f'<tr><td>{esc(workload["name"])}</td>'
                f'<td class="num">{workload.get("threads") or ""}</td>'
                f'<td class="num">{f"{runtime * 1000:.0f} ms" if runtime else ""}</td>'
                f'<td class="iter">{esc(" · ".join(f"{r * 1000:.0f}" for r in runs))}</td></tr>')
    if timing:
        parts.append('<h3>Per-workload timing (ms)</h3>'
                     '<table class="timing"><tr><th>Workload</th><th>Threads</th>'
                     '<th>Runtime</th><th>Iterations</th></tr>' + "".join(timing) + '</table>')
    parts.append('</details>')
    return "\n".join(parts)


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

    groups = [g for g in ("single", "multi", "gpu") if getattr(report, g)]
    if groups:
        parts.append('<div class="scores">')
        for g in groups:
            label = {"single": "Single-Core", "multi": "Multi-Core", "gpu": "Compute"}[g]
            parts.append(
                f'<div class="card"><div class="label">{label} Score</div>'
                f'<div class="value">{fmt(getattr(report, g)["score"])}</div></div>'
            )
        parts.append("</div>")

    metrics = dict(report.metrics)
    gpu_api = report.details.get("gpu_api")
    for key, label in (("gpu_platform_name", "GPU Platform"), ("gpu_device_name", "GPU Device")):
        value = report.details.get(key)
        if value not in (None, "", -1):
            metrics[label] = value
    if gpu_api not in (None, "", -1):
        metrics["GPU API"] = GPU_APIS.get(gpu_api, str(gpu_api))
    rows = list(metrics.items()) if metrics else [
        (LABELS[k], report.info[k]) for k in ("model", "cpu", "cores", "memory", "os", "version")
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
            detail = rate_string(w["name"], w.get("rate"))
            if not detail and w.get("runtime"):
                detail = f'{w["runtime"] * 1000:.0f} ms'
            parts.append(
                f'<tr><td class="name">{esc(w["name"])}</td>'
                f'<td class="score">{fmt(w["score"])}'
                f'<br><span class="desc">{esc(detail)}</span></td>'
                f'<td class="bar"><div class="track"><div class="b" style="width:{width}%"></div></div></td></tr>'
            )
        parts.append("</table>")

    parts.append(_details_block(report, groups))
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
    title = str(report.metrics.get("Model")
                or report.info.get("model")
                or report.info.get("cpu")
                or path.rsplit("/", 1)[-1])
    return report, to_html(report, title)
