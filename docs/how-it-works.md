# How it works

## The two constraints of the free build

1. **Upload is mandatory.** The console build exits 255 after a failed upload and
   never prints the summary. `--no-upload`, `--save`, `--json`, `--export-*`
   are gated behind `only available in Geekbench 7 Pro`.
2. **The result window is remote.** The GUI embeds a web view of
   `https://browser.geekbench.com/v7/cpu/<id>`; blocking the upload yields
   "Unable to display benchmark results". `File → Save` is disabled because no
   document is created.

## The trick

Instead of blocking, redirect. The client posts a multipart body to
`https://browser.geekbench.com/...`; patch the host string to `127.0.0.1:PORT`
and force the URL builder's plain-http branch, and the same POST arrives at a
local server. The client believes it uploaded; the data is on your disk.

```
POST / HTTP/1.1
Content-Type: multipart/form-data; boundary=0xKhTmLbOuNdArY

--0xKhTmLbOuNdArY
Content-Disposition: form-data; name="document"

{ "document_type": 0, "document_version": 7, "sections": [...], "score": 3648, ... }
--0xKhTmLbOuNdArY
Content-Disposition: form-data; name="hash"

…
--0xKhTmLbOuNdArY--
```

The `document` part is the full result: `sections[]` (each with `workloads[]`,
`score`, `metrics`), plus `score` / `multicore_score`, system info and run
options. That is everything needed to render locally.

## Result document shape (7.1.0, observed)

```jsonc
{
  "document_type": 0,
  "document_version": 7,
  "platform": { "os": "macOS", "architecture": "aarch64", "bits": 64 },
  "processor_frequency": { "frequencies": [ … ] },
  "metrics": [ … ],
  "score": 3648,               // single-core
  "multicore_score": 17428,
  "sections": [
    { "name": "Single-Core", "score": 3648,
      "workloads": [ { "name": "File Compression", "score": 3064, "rate": "…" } ] },
    { "name": "Multi-Core",  "score": 17428, "workloads": [ … ] }
  ]
}
```

`render.py` does not depend on this shape: it walks the tree, recognises
`single`/`multi` by key or section name, and pulls `workloads`/`metrics`/`tests`
lists. Geekbench 6 `.gb6` files and browser exports parse through the same path.

## Binary patch

```
browser.geekbench.com     21 bytes, read-only string table
127.0.0.1:8080 + NULs     21 bytes, no offsets shift
```

Scheme switch — compiler output for the URL builder:

```
ldrb  w8, [x22, #0x50]     ; https flag
cmp   w8, #1
b.ne  http_branch          ; ← we rewrite this to "b http_branch"
mov   w8, #8               ; strlen("https://")
mov   x8, #0x7468          ; "ht"
movk  x8, #0x7074, lsl #16 ; "tp"
movk  x8, #0x3a73, lsl #32 ; "s:"
movk  x8, #0x2f2f, lsl #48 ; "//"
```

We search for the `movk` word and flip the preceding `b.ne` to an unconditional
branch. Same instruction on ELF/PE builds compiled from the same source.

## Why local results are still correct

Benchmarks run in-process. The upload happens *after* `Finished benchmark run`,
so patching the destination cannot influence measurements; it only changes
where the result goes.

## Rendering

`render.py` produces a self-contained light/dark HTML page (score cards, system
table, per-workload bars, throughput strings) and a terminal table. No network,
no fonts, no JS.
