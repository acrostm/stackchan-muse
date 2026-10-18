# Contributing / 贡献

Use small pull requests with the problem, behavior change, tests and hardware impact. Follow applicable `AGENTS.md` instructions under `firmware/`. Keep upstream notices and record upstream imports by commit; do not mix vendor refreshes with behavior changes.

提交应说明问题、行为变化、测试证据及硬件影响。使用短分支和 PR；上游同步与业务修改分开提交。

Before opening a PR:

1. Run `python3 tools/check_repository.py` after staging and the project tests.
2. For firmware changes, build both supported profiles and run upstream tests. Report skips and limitations.
3. Never commit private configuration, device identities, recordings, factory images or account-enabled binaries.
4. Motion, audio, NVS/partition, OTA and power changes require targeted hardware evidence before release. CI alone is insufficient.
5. Document recovery and configuration migration. Do not burn eFuses or flash connected hardware from CI.

The public upstream development signing key is a fixture, not a production identity. Custom signing keys belong outside Git. Keep dependencies and CI actions pinned, and update lock files intentionally.
