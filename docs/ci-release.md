# CI and release policy / CI 与发布门禁

## Required checks

The aggregate `Quality gate` checks repository policy, project tests, upstream tests, the UI simulator and both StackChan/CoreS3 token-free builds. Firmware builds include IDF's partition-size check. Test failures, unexpected upstream skips, failed jobs and missing artifacts fail the aggregate gate.

Normal CI has read-only repository access, no user credentials, bounded job timeouts and cancellation for superseded runs. It never pairs, flashes, calls paid providers or modifies hardware. Build outputs are allowlisted into bundles; sdkconfig, ELF files, logs and private keys are not packaged. Only the inherited public development signing fixture remains in Git.

GitHub branch/ruleset enforcement depends on the account plan and repository visibility. A configured workflow alone does not enforce branch protection. The setup result and any API limitation must be reported explicitly. CODEOWNERS review and a passing `Quality gate` are the intended merge requirements; automatic merging is disabled.

## Release

There is currently **no hardware-approved release**. The manual draft-release workflow is deliberately blocked without a real report. It reruns the quality gate, checks a committed JSON report against the current `firmware`, `companion` and `tools` Git trees, and requires every hardware acceptance item to be true. Reports must include a non-empty evidence reference and board name; never include credentials or full device identifiers.

Template (replace values with real evidence, never set fields true to bypass testing):

```json
{
  "board": "stackchan",
  "firmware_tree": "<git rev-parse HEAD:firmware>",
  "companion_tree": "<git rev-parse HEAD:companion>",
  "tools_tree": "<git rev-parse HEAD:tools>",
  "evidence": "<redacted hardware test report path or URL>",
  "checks": {
    "muse_pairing": false,
    "voice_roundtrip": false,
    "tts_playback": false,
    "touch_stop": false,
    "head_limits": false,
    "head_emergency_stop": false,
    "reconnect": false,
    "twenty_turns": false,
    "two_hour_stability": false,
    "recovery": false
  }
}
```

Dispatch from main with a version such as `v0.1.0`, the report's repository path under `docs/hardware-validation/`, and explicit confirmation. The `firmware-release` environment is a place for approval; required-reviewer enforcement must be configured separately if the plan supports it. The workflow creates a **draft**, never a published release, using account-free bundles and SHA-256 checksums.

This checks recorded human evidence, not the truth of physical experiments. A code/tree change invalidates the report. CI cannot certify a device as bug-free. Personal-token binaries remain local even after release.

## Other operational concerns

- First flash: identify hardware, verify a complete backup, inspect partition migration, calibrate motion and test recovery.
- OTA: keep a known-good image, validate rollback and do not enable it as an unattended release action.
- Stability: record 20-turn acceptance and two-hour stability before an MVP candidate; retain longer soak testing for daily-use releases.
- Privacy and cost: no raw audio/images in logs; bounded TTS requests; live provider calls are opt-in local checks.
- Supply chain: preserve upstream licenses/artwork restrictions, commit pins and managed-component lock snapshots; review dependency updates.
- Device identity: no MACs, serials or personal network details in reports.
