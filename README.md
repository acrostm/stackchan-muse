# MuseStack — StackChan × Muse

[简体中文](README.zh-CN.md) · [English](README.md)

Turn a CoreS3-based StackChan into a physical terminal for your existing Muse: voice conversation, spoken Chinese replies, expressions and controlled head motion. Muse remains the agent; this project does not substitute another model.

**Development snapshot, not a ready-to-flash release.** A CoreS3 text-reply probe is flashed and boots; built-in speaker playback is confirmed by the owner. Muse pairing and the Chinese voice round trip pass on hardware; network access remains dependent on a working LAN proxy or relay. See [capability evidence](docs/capabilities.json) and [implementation notes](docs/implementation-status.md).

## Status

| Area | Evidence | Remaining work |
|---|---|---|
| Recovery | Two matching 16 MiB backups; full restore write/hash verification and factory boot passed | Full factory feature regression |
| Firmware | StackChan baseline builds on ESP-IDF 6.0.1; 47% app-slot headroom | CoreS3 probe boots with 8 MiB PSRAM; conversation verification pending |
| Host checks | 143 upstream tests, one skipped; 47 project tests pass locally | CI results are recorded separately |
| Chinese speech | Direct Doubao playback and a real 1.80 s voice reply passed on hardware | Longer replies and fault injection on hardware |
| Muse | Pairing, microphone input, assistant text and spoken reply passed on hardware | Personal context, tool permissions, history and reconnect cases |
| Expressions / head | Finished reply text selects small local gestures; explicit per-unit NVS calibration, one priority arbiter, speed limiting and emergency stop are implemented | Per-unit hardware calibration and motion capture |
| Camera / ambient perception | An explicit StackChan camera profile compiles one GC0308 still capture at a time | Real frame capture, streaming, tracking and concurrent audio/vision remain unverified |

Wake words, tracking and duplex speech are not part of the current verified
build.

## Interaction and setup

- Hold the talk control for more than two seconds. A short tap, an unreleased
  recording or a cancelled recording never enters the upload queue.
- Open **Browser setup / proxy / voice** from the Wi-Fi settings page. The
  device exposes a local `Muse-Setup-XXXXXX` access point, a persistent
  eight-digit PIN and `http://192.168.4.1`.
- Muse traffic can use a per-SSID SOCKS5/Clash proxy. The proxy must be on the
  private LAN and accept that device; other destination names and Doubao TTS
  stay direct. TLS still verifies the official server identity.
- Muse final messages received while the gadget is idle enter a small bounded
  notification queue. The gadget wakes, chirps, speaks the text and shows it as
  a caption. This path is implemented, but server delivery of every phone and
  scheduled-task message still needs account-level observation.

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

Add `--with-camera` when testing the CoreS3 GC0308 still-camera path. It remains experimental until capture is verified on the attached StackChan.

TTS bridge: `python3 -m companion.tts_server` binds loopback by default. See [bridge instructions](companion/README.md); using it on-device temporarily requires a reachable host. Standalone speech remains an integration goal.

## Quality and delivery gates

PRs and main pushes run repository/secret checks, project tests, upstream host tests, the UI simulator, and token-free StackChan/CoreS3/Waveshare C6 builds with partition size checks. CI never flashes hardware, calls paid providers, pairs accounts or receives personal credentials. Build bundles contain checksums and source provenance.

Release automation requires a matching source-tree hardware report, all CI jobs, explicit human confirmation and the `firmware-release` environment. It creates a **draft** release only. This is a process gate, not automatic proof of hardware correctness. See [CI and release policy](docs/ci-release.md).

## Hardware precautions and privacy

Identify the board and servos, keep a verified factory backup and calibrate before motion. Never enable irreversible eFuses during ordinary development. Do not expose the local bridge publicly; its LAN HTTP mode is not encrypted. Raw audio, images, account tokens, Wi-Fi credentials and factory images stay out of Git and CI artifacts.

## Contributing and license

Read [CONTRIBUTING](CONTRIBUTING.md), [SECURITY](SECURITY.md), [recovery](docs/recovery.md) and [NOTICE](NOTICE). Code uses [Apache-2.0](LICENSE), subject to original third-party licenses. The upstream Jollybot artwork has separate terms and is **not** relicensed here. This is an independent personal project, not an official Meta or M5Stack product.

Proactive messages and scheduled-task announcements are tracked in [the notification scope](docs/proactive-messages.md). Background delivery and device playback are not implemented or verified yet.
