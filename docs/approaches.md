# Ways to run Geekbench without sending results upstream

There is more than one way to get a benchmark that runs offline and still shows
you a score. This page lists the approaches we evaluated, how far each one gets,
and why the project ships the one it does.

Columns:
**Offline** = benchmark can run with no internet · **Result** = you can see the
score locally · **Net** = needs a network namespace / DNS change ·
**Implemented** = what this repo does today.

| # | Approach | Offline | Result | Root needed | Implemented |
| --- | --- | --- | --- | --- | --- |
| A | Loopback fake endpoint, host string patched, HTTP forced | ✅ | ✅ rendered HTML | — | ✅ default |
| B | Loopback fake endpoint over HTTPS + trusted local CA | ✅ | ✅ | GUI consent | ✅ `--keep-https` + `--https-port` |
| C | Blackhole the upload host (hosts / firewall) | ⚠️ client complains | ❌ *Unable to display* | sudo | ✅ "offline" mode (`--zzz`) |
| D | Transparent proxy / mitmproxy | ✅ | ✅ | CA trust | ✋ possible, not shipped |
| E | Force the Pro-only `--no-upload` path | ✅ | ⚠️ CLI summary only | — | ❌ licence bypass, out of scope |
| F | Patch control flow to skip the upload call | ✅ | ⚠️ depends on build | — | ✋ fragile, not shipped |
| G | Redirect upload to `file://` or a unix socket | ✅ | ⚠️ | — | ✋ needs code work |
| H | Hook the process (DYLD / Frida) and dump the result object | ✅ | ✅ | SIP/DYLD rules | ✋ research path |
| I | Reverse the response schema so the client opens its own window | ✅ | ✅ native | — | ⏳ known gap, PRs welcome |
| J | Point the result web view at a local file | ✅ | ✅ | — | ✋ equivalent outcome to A |
| K | Buy the Pro licence | ✅ | ✅ native | — | — (vendor path) |
| L | Use another benchmark | ✅ | ✅ | — | — |

## A. Loopback fake endpoint with the host string patched — the default

Replace `browser.geekbench.com` with `127.0.0.1:8080` inside the executable and
force the URL builder's plain-http branch. The client uploads normally; a local
server stores the multipart body, extracts the `document` JSON and renders a page.

- Pros: client stays happy, no CA, no root, reversible (patch a copy).
- Cons: the client's *own* result window still validates the response and shows
  "Unable to display benchmark results" — the local HTML is the result.
- Status: verified on Geekbench 7.1.0 / macOS 26 (arm64 + x86_64).

## B. Same, but over HTTPS with a local CA

Do not force the http branch; instead serve TLS on `127.0.0.1:8443` with a
certificate for `127.0.0.1`, signed by a CA the client trusts.

- Pros: keeps the original scheme logic; closer to upstream behaviour.
- Cons: the CA must be trusted by the *system*; recent macOS silently ignores
  `security add-trusted-cert` from headless sessions, and a CA without
  `basicConstraints=CA:TRUE` is permanently `CSSMERR_TP_CERT_SUSPENDED`.
- Status: server side implemented (`--https-port`, `--cert`, `--key`); trust is
  the operator's problem.

## C. Blackhole the upload host

`/etc/hosts` → `127.0.0.1` or `0.0.0.0`, or a firewall drop rule.

- Pros: zero binary edits, one line, works for any version.
- Cons: the client treats the failure as fatal — CLI exits 255 without printing
  the summary, GUI shows "Unable to display benchmark results". You get silence,
  not a score.
- Status: implemented as `--zzz` mode for people who only need "nothing leaves
  the machine".

## D. Transparent proxy / mitmproxy

Point the system proxy at a local MITM, intercept the POST, return a stub.

- Pros: no binary edits; can also inspect other clients.
- Cons: TLS interception requires trusting the proxy CA (same TCC problem), and
  the proxy must be running for every benchmark.
- Status: not shipped; the fake endpoint covers the same ground with fewer moving
  parts.

## E. Unlock the Pro-only `--no-upload` path

Patch the licence check so `--no-upload`, `--save`, `--export-json` work.

- Pros: native offline behaviour, real `.gb7` files.
- Cons: that is licence bypass. This project does not implement it, and the
  `--zzz` mode already covers "no data leaves the machine".
- Status: deliberately out of scope.

## F. Patch control flow to skip the upload

Neutralise the call that starts the upload, keep printing the summary.

- Pros: no server, no ports.
- Cons: the summary printer and the upload share state; a naive patch yields
  `Run completed without associated document` or a crash. Needs per-build
  reverse engineering.
- Status: not shipped.

## G. Redirect the upload to `file://` or a unix socket

Same host swap, different transport.

- Pros: no listening port.
- Cons: the client builds an `https://` URL; scheme and transport handling still
  have to be patched, and CFNetwork will not POST to `file://`.
- Status: not shipped.

## H. Hook the process and dump the result object

DYLD interposition (unhardened builds) or Frida; export the in-memory result.

- Pros: no server, no patch of the bundle.
- Cons: needs library-validation exceptions, breaks with hardened runtimes, one
  hook per version.
- Status: research path; the uploaded `document` JSON is the same data and much
  easier to obtain (approach A).

## I. Reverse the upload response schema

The client parses our JSON and still reports
`Unable to parse server response: JSON value is not an integer`. Find the exact
field set and its own result window opens again.

- Pros: fully native UX, no local HTML needed.
- Cons: unknown schema; trial and error costs a 4-minute benchmark per attempt.
- Status: **open gap** — see `docs/pitfalls.md` §7. If you have a packet capture
  from a real upload, that is the fastest way in.

## J. Point the client's web view at a local file

Instead of a fake server, rewrite the URL the result window loads.

- Pros: no ports.
- Cons: the URL is produced by the same code path that builds the upload URL;
  patching it affects both.
- Status: not shipped; approach A already yields the same page.

## K/L. Buy Pro, or use another benchmark

Worth saying out loud. If you need the vendor's own offline mode and native
results, a licence is the supported route. If you need a number and not
Geekbench specifically, other tools may fit better.

---

## Choosing

```
need "nothing leaves the machine only"        → C  (--zzz)
need a local score page, no root, no CA       → A  (default)
need TLS fidelity / auditing                  → B  or D
need native result window                     → K, or contribute to I
```
