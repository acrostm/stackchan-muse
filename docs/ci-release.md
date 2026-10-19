# CI and release policy / CI 与发布门禁

## Required checks

The aggregate `Quality gate` checks repository policy, project tests, upstream tests, the UI simulator and token-free StackChan, StackChan-camera, CoreS3 and Waveshare C6 builds. The C6 build covers the supported no-PSRAM startup path; the camera matrix entry compiles the GC0308 still-capture path. Firmware builds include IDF's partition-size check. Test failures, unexpected upstream skips, failed jobs and missing artifacts fail the aggregate gate.

Normal CI has read-only repository access, no user credentials, bounded job timeouts and cancellation for superseded runs. It never pairs, flashes, calls paid providers or modifies hardware. Build outputs are allowlisted into bundles; sdkconfig, ELF files, logs and private keys are not packaged. Only the inherited public development signing fixture remains in Git.

The public repository's main branch is protected, including administrators: changes require a pull request, strict passing `Quality gate` and `OpenAI review gate` checks, resolved conversations and linear history. Direct pushes, force pushes and branch deletion are prohibited. Automatic merging is disabled.

The Codex gate accepts only the official `chatgpt-codex-connector[bot]` native structured summary with `status=completed`, the exact full current `commit_sha`, `has_any_findings=false` and `has_unresolved_findings=false`. This is the native result observed on PR #2. Formal GitHub approvals, custom verdict markers, generic comments and reactions are deliberately not alternative approval sources. Pending, negative, malformed and stale native results block merging.

The verifier runs from protected/default-branch events (`pull_request_target`, `issue_comment`, or a maintainer dispatch) and checks out only protected base code. Native summary creation, edits and deletion trigger rechecks independently of PR-modifiable workflow definitions. There is no PR-side review-signal dependency. Fork contributions currently need a maintainer branch before approval.

Official Codex integration is confirmed connected by its authenticated review result on PR #2; a request comment alone does not prove that it is enabled. See [OpenAI's GitHub review guide](https://developers.openai.com/codex/integrations/github). The gate does not implement an alternate API reviewer. Until its workflow is installed on main and a genuine approval is verified, a missing gate blocks merging. Bootstrap must not disable branch protection or fabricate approval.

中文：main 已启用包含管理员在内的分支保护，只能通过 PR 合并，且需要质量门禁和当前提交的官方 Codex 明确审批。机器人表情、普通评论、旧提交审批不能放行。首次安装门禁也不允许关闭保护或伪造成功；未取得当前提交明确结果时保持阻止合并。

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
