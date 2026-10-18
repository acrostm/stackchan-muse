# Development / 开发

## Environment

Use ESP-IDF **v6.0.1**, target ESP32-S3, 16 MiB Flash, CoreS3 quad PSRAM. Source and managed-component versions are recorded in `upstream-lock.json` and `firmware-dependencies.lock.yml`.

`tools/build_firmware.py` is a convenience wrapper for the current Mac layout: IDF at `.toolchains/esp-idf`, tools at `.toolchains/tools`, IDF Python at `python_env/idf6.0_py3.14_env`, and the recorded Xtensa toolchain version. It removes proxy environment variables at the user's request. On other machines use an activated IDF environment and the README commands. A fresh directory and absolute SDKCONFIG path avoid stale board settings.

CI uses the official `espressif/idf:v6.0.1` image. This version tag is fixed, but its registry digest is not yet pinned; source versions and artifact checksums are recorded separately. Action references are commit-pinned. Do not claim bit-for-bit reproducibility: compiler timestamps and signing can affect outputs.

## Tests

```sh
python3 -m unittest discover -s tests -v
# After an IDF configure/build installs managed cJSON:
cd firmware/esp32
python -m unittest discover -s tests -p 'test_*.py' -v
```

Upstream tests can use `CJSON_SOURCE_DIR` and `IDF_PATH`. Real crypto vectors need the Python `cryptography` package; Noise Core host tests need PSA Crypto development headers/libraries. Always report skips. CI installs these dependencies, treats unexpected skips as a failed gate, and never substitutes a fake crypto implementation.

## Configuration and data

`python3 tools/init_config.py` creates a 0600 file under the private 0700 directory and refuses to overwrite it. Logs and account-enabled build outputs stay private. Normal CI receives no account secrets and runs no live Muse/Doubao calls.

The generic baseline requires a user's SDK token before pairing; compiled personal-token firmware is not a redistributable artifact. The bridge starts on loopback; a LAN binding must be explicit.

## Vendor maintenance

`firmware/` is a source snapshot, not a Git submodule. Preserve licenses and notices, record the upstream commit, and review imports separately. Before syncing vendor source, review camera status, motion defaults, pairing compatibility, partitions, OTA rollback and artwork terms. Do not copy local managed components, sdkconfig files or signing material into a snapshot.
