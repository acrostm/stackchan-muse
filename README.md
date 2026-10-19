# MuseStack — StackChan × Muse

[简体中文](README.zh-CN.md) · [English](README.md)

Turn a CoreS3-based StackChan into a physical terminal for your existing Muse: voice conversation, spoken Chinese replies, expressions and controlled head motion. Muse remains the agent; this project does not substitute another model.

**Development snapshot, not a ready-to-flash release.** No custom firmware has been flashed. See [capability evidence](docs/capabilities.json) and [implementation notes](docs/implementation-status.md).

## Status

| Area | Evidence | Remaining work |
|---|---|---|
| Recovery | Two complete 16 MiB factory reads match | Restore write test |
| Firmware | StackChan baseline builds on ESP-IDF 6.0.1; 47% app-slot headroom | Account-enabled probe and hardware verification |
| Host checks | 143 upstream tests, one skipped; 24 project tests pass locally | CI results are recorded separately |
| Chinese speech | Real Doubao synthesis returns 24 kHz mono MP3 | Device speaker, cancellation and timeout handling |
| Muse | Official SDK and pairing paths retained | Pairing, voice round trip, personal context and tools |
| Expressions / head | Upstream drivers available | Real-event integration, calibration, limits and arbitration |
| Camera / ambient perception | Experimental upstream capture is not usable | Future work; no vision claim |

Wake words, tracking, duplex speech and task notifications are not part of the current verified build.

## Repository

- `firmware/`: vendored upstream source snapshot; provenance in [upstream-lock.json](docs/upstream-lock.json).
- `companion/`: bounded Doubao TTS client and authenticated, optional local bridge.
- `tools/`: local build, backup and repository checks.
- `tests/`: project host tests; upstream tests live in `firmware/esp32/tests/`.
- `docs/`: plan, evidence, dependency lock, recovery and release policy.
- `.private/`, `backups/`, `.toolchains/`, `build-*/`: local only, never committed.

Vendoring keeps project changes reviewable in this repository. Upstream history is identified by commit; it is not a nested Git submodule.

## Local development

Use Python 3.10+, a C/C++ compiler and **ESP-IDF v6.0.1**. The existing local build helper expects the project-local toolchain described in [development](docs/development.md). A normal activated IDF environment can build directly:

```sh
python3 tools/init_config.py
python3 -m unittest discover -s tests -v
cd firmware/esp32
idf.py -B build-stackchan -DIDF_TARGET=esp32s3 \
  -DSDKCONFIG="$PWD/build-stackchan/sdkconfig" \
  -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;devices/sdkconfig.muse;devices/sdkconfig.muse-m5stack-stackchan" build
```

Enter your own Muse SDK token and Doubao credentials **only** in `.private/config.json`. Initialization refuses to overwrite an existing configuration. The baseline build above has no account token and is not an account-ready binary. For the project-local setup, `python3 tools/build_firmware.py --with-token` embeds your local token; keep its outputs private.

TTS bridge: `python3 -m companion.tts_server` binds loopback by default. See [bridge instructions](companion/README.md); using it on-device temporarily requires a reachable host. Standalone speech remains an integration goal.

## Quality and delivery gates

PRs and main pushes run repository/secret checks, project tests, upstream host tests, the UI simulator, and token-free StackChan/CoreS3 builds with partition size checks. CI never flashes hardware, calls paid providers, pairs accounts or receives personal credentials. Build bundles contain checksums and source provenance.

Release automation requires a matching source-tree hardware report, all CI jobs, explicit human confirmation and the `firmware-release` environment. It creates a **draft** release only. This is a process gate, not automatic proof of hardware correctness. See [CI and release policy](docs/ci-release.md).

## Hardware precautions and privacy

Identify the board and servos, keep a verified factory backup and calibrate before motion. Never enable irreversible eFuses during ordinary development. Do not expose the local bridge publicly; its LAN HTTP mode is not encrypted. Raw audio, images, account tokens, Wi-Fi credentials and factory images stay out of Git and CI artifacts.

## Contributing and license

Read [CONTRIBUTING](CONTRIBUTING.md), [SECURITY](SECURITY.md), [recovery](docs/recovery.md) and [NOTICE](NOTICE). Code uses [Apache-2.0](LICENSE), subject to original third-party licenses. The upstream Jollybot artwork has separate terms and is **not** relicensed here. This is an independent personal project, not an official Meta or M5Stack product.
