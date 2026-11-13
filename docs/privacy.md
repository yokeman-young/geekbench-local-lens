# Privacy: why results are sensitive, and how to scrub them

A Geekbench document looks like numbers, but it is closer to a device
fingerprint.

| Field | What it leaks |
| --- | --- |
| `system_uuid`, `uuid` | stable machine identity across runs |
| `metrics[].value` | OS build, compiler version, model identifier (`Mac17,3`, `iPhone17,1`) |
| `processor_frequency.frequencies` | thermal curve — near-unique per unit |
| `date`, `runtime`, `clock` | when the machine ran, for how long, at what clocks |
| `sections[].workloads[].score` | the score vector itself is surprisingly identifying when combined with the above |

Sharing a raw `.gb7` publicly is roughly equivalent to posting a hardware
serial with a timestamp.

## Scrub before you share

```bash
gblens scrub result.gb7                       # strict (default)
gblens scrub result.gb7 --level light         # keep versions, drop identifiers
gblens --json scrub result.gb7 --out clean.json
```

`--level strict` (default) removes identifiers *and* rewrites version strings,
model ids, frequency arrays and run timings. `light` only drops the identifier
keys, which is what you want when the OS/compiler version is the point of the
comparison.

Library use:

```python
from gblens import scrub
from gblens.render import parse_document

clean = scrub.scrub(raw_document, level="strict")
report = parse_document(clean)     # still renders: sections/scores are kept
```

## What scrub changes

Removed keys: `system_uuid`, `uuid`, `serial*`, `hostname`, `username`, `user`,
`email`, `checksum`, `commit`, `date`, `timestamp`, `runtime`, `clock`, `build`,
`branch`, `token`, `license*`, machine/board ids, IP/MAC.

Rewritten in `strict` mode: `1.2.3`/`Build 26B131` → `<version>`, `Mac17,3` →
`<model-id>`, `frequencies` array → `<redacted>`.

Kept: `document_type`, `options`, `platform` (os/arch/bits), `sections`,
`workloads`, `score`, `multicore_score` — everything the renderer needs.

## Repository policy

- `examples/results/*.json` are generated with `gblens scrub --level strict`;
  CI asserts the fixture has no `uuid`/`date`/`runtime`/`clock`, that
  `frequencies` is `<redacted>` and the model id is `<model-id>`.
- Commit metadata uses a project identity, not a personal address.
- Do not attach raw uploads (`results/*.json` from the server) to issues — they
  contain the full document. Run `gblens scrub` first.

## Residual risk

Strict scrubbing does not anonymise the *performance profile*: a 10-core M5 at a
given clock curve with a specific workload vector can still be correlated. If
that matters, perturb or omit the per-workload numbers; `--level strict` keeps
them deliberately, because fixtures exist to test the parser.
