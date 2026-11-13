# Pitfalls (learned the hard way)

Each item cost real debugging time; keeping them here saves the next person.

## 1. Never patch or re-sign the embedded runner

`Contents/Resources/geekbench_aarch64` / `geekbench_avx2` are the GUI's
benchmark engines. Patching them and re-signing individually makes the GUI
cancel every run instantly:

```
Run completed without associated document. Cancelled?
```

Patch only `Contents/MacOS/<executable>`; the whole-bundle `--deep` re-sign is
fine.

## 2. `--options linker-signed` is required for code edits

After editing the code segment, a plain `codesign --force --sign -` fails with:

```
main executable failed strict validation
```

Add `--options linker-signed`. Data-only edits (string table) do not need it.

## 3. Do not delete `SUFeedURL`, redirect it

Removing the Sparkle feed key breaks NSDocument association in the app
(`Run completed without associated document`). Point it at an invalid host and
disable automatic checks instead.

## 4. A CA without `CA:TRUE` is never trusted

`openssl req -x509` under LibreSSL omits `basicConstraints`. macOS then reports
`CSSMERR_TP_CERT_SUSPENDED` no matter how many times you trust it. Generate the
root with an explicit config:

```
[v3_ca]
basicConstraints = critical, CA:TRUE
keyUsage = critical, keyCertSign, cRLSign
```

## 5. Trust settings cannot be written from a non-GUI session

`security add-trusted-cert` returns 0 but leaves `Number of trust settings : 0`
when called from a headless agent; `SecTrustSettingsSetTrustSettings` reports
"authorization was denied since no user interaction was possible". Killing
`trustd`/`securityd` does not help. Either use the Keychain GUI or skip TLS
entirely (that is why this project forces the http branch).

## 6. `curl` does not test macOS trust

`curl` validates against `/etc/ssl/cert.pem`, not the Keychain. Use
`security verify-cert -c server.pem -p ssl`.

## 7. The client validates the upload response

Our endpoint returns a superset JSON, yet the client still logs:

```
Results upload finished with view URL:(null), claim URL:(null),
error:Geekbench Code=5000 { PLResultUploadOperationUploadErrorKeyErrorString = … }
```

and shows the "Unable to display" page. The upload has already been stored —
treat `results/*.html` as the source of truth. If you pin down the expected
schema, PRs are welcome (`server.py`, `do_POST`).

## 8. App Management TCC blocks in-place edits of an installed .app

Writing directly into an existing bundle under `~/Applications` can fail with
`Operation not permitted`. Always build into a temp directory and `mv` it into
place (the `patch` command does this).

## 9. UI automation needs real mouse events

`AXPress` on Geekbench's "Run CPU Benchmark" button is accepted but does nothing;
only a real click works, which requires Accessibility permission (reset after
reboot). Expect to click manually when the agent's TCC grant is missing.

## 10. `--no-upload` is Pro-gated

```
Error: The `--no-upload` switch is only available in Geekbench 7 Pro.
```

This project does not unlock Pro. It fixes *where* the upload goes, not *whether*
a licence exists.
