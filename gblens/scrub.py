"""Strip identifying material from Geekbench results before sharing them.

A Geekbench document is more revealing than it looks:

* ``system_uuid`` / ``uuid`` identify the machine across runs
* ``metrics`` carries the OS build, compiler version, model identifier
* ``processor_frequency.frequencies`` is a near-unique thermal fingerprint
* ``date`` / ``runtime`` narrow down when and how long the machine ran
* even the score vector itself is fairly unique when combined with the above

``scrub`` keeps the *shape* of the document (sections, workloads, scores) so a
fixture stays useful for parser tests, while removing the parts that point back
at a person.
"""
from __future__ import annotations

import re
from typing import Any

# Keys removed outright — they either identify the machine or are metadata we
# never need for rendering/tests.
DROP_KEYS = {
    "system_uuid", "uuid", "serial", "serialnumber", "hardware_uuid",
    "hostname", "username", "user", "email", "checksum", "commit",
    "date", "timestamp", "createdat", "uploaddate", "runtime", "clock",
    "build", "branch", "token", "license", "licenseemail", "licensekey",
    "machine_id", "board_id", "oem_id", "ip", "mac", "signature",
}

# Keys whose string values may embed build numbers / versions.
SOFT_KEYS = {"value", "name", "version", "os", "platform"}

VERSION_RE = re.compile(r"(\d+\.){1,3}\d+|\bBuild\s+\w+\b|\bBuild\s*\(\w+\)")
MODEL_ID_RE = re.compile(r"^[A-Za-z]{2,4}\d{1,3},\d{1,2}$")


def _clean_value(value: str, level: str) -> str:
    if level != "strict":
        return value
    cleaned = VERSION_RE.sub("<version>", value)
    if MODEL_ID_RE.match(cleaned.strip()):
        return "<model-id>"
    return cleaned


def scrub(document: Any, level: str = "light") -> Any:
    """Return a scrubbed copy of ``document``.

    level="light"  – drop identifiers, keep hardware family and scores (default)
    level="strict" – additionally strip version strings, model ids, frequency
                     arrays and run timings
    """
    if isinstance(document, dict):
        out = {}
        for key, value in document.items():
            if key.lower() in DROP_KEYS:
                continue
            if level == "strict" and key.lower() in ("frequencies", "frequency"):
                out[key] = "<redacted>"
                continue
            out[key] = scrub(value, level)
        return out
    if isinstance(document, list):
        return [scrub(item, level) for item in document]
    if isinstance(document, str):
        return _clean_value(document, level)
    return document


def summarise(original: Any, cleaned: Any) -> dict:
    """Rough diff so a caller can report what was removed."""
    def count_keys(node: Any) -> int:
        if isinstance(node, dict):
            return len(node) + sum(count_keys(v) for v in node.values())
        if isinstance(node, list):
            return sum(count_keys(v) for v in node)
        return 0

    return {
        "keys_before": count_keys(original),
        "keys_after": count_keys(cleaned),
        "removed": max(0, count_keys(original) - count_keys(cleaned)),
    }
