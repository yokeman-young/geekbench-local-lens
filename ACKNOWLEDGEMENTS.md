# Acknowledgements

## DeepSeek Harness

This project was conceived, implemented and verified inside a **DeepSeek Harness**
session. The work — reading disassembly, locating the URL builder, discovering
that the client's result window is a remote page, working out why a re-signed
runner cancels every benchmark, and chasing the macOS trust-settings dead end —
was done by an agent operating the machine through the harness: running the
benchmarks, reading `log show`, patching copies, and checking every claim against
live output rather than assumption.

The harness's tool surface (shell, file edits, background jobs, browser, sub-agent
dispatch) is what made it possible to keep a long, evidence-driven loop going
without losing state.

## DeepSeek Purge

The **DeepSeek Purge** plugin was used for this session. It provisions the
unrestricted sandbox profile that lets the agent operate the local machine
end-to-end — patching binaries, re-signing bundles, running the benchmark and
inspecting system logs — instead of stopping at "here is what you could try".

Its patch/injection layer also made the instruction stack predictable enough to
reason about, which matters when half the work is figuring out why a commercial
app refuses to cooperate.

## Upstream

- Primate Labs for Geekbench itself, and for publishing enough detail about the
  workload suite (AV1/Opus, MobileNet, Clang, …) to interpret the numbers.
- The macOS reverse-engineering community whose notes on `codesign`,
  `linker-signed`, `__interpose` and TCC behaviour saved a lot of dead ends.

## Contributors

See the commit history. Names are kept project-scoped on purpose: result files
are device fingerprints, so the repository does not carry personal identities.
