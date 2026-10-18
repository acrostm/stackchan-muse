# Security / 安全

Do not file public issues containing tokens, raw recordings, factory backups or full device identifiers. Use the repository's private vulnerability reporting feature when enabled; otherwise contact the repository owner privately without posting exploit details publicly.

不要在公开 issue 中提交密钥、录音、原固件或完整设备标识。优先使用 GitHub 私密漏洞报告；未开放时先通过私下渠道联系仓库所有者。

Only current development is maintained; no production security or uptime guarantee is made. The bridge is for a trusted private network, requires a dedicated token and defaults to loopback. LAN HTTP is unencrypted. Do not port-forward it.

Never put Muse or provider credentials in Actions secrets for normal CI. CI builds are account-free. A firmware binary built with an account token is itself sensitive. Rotate credentials if exposed; deleting a file from the latest commit does not remove it from history.

No unattended hardware writes, production deployments, eFuse changes or automatic public releases. The development signing key shipped by upstream is intentionally public and must not be treated as a production trust root.
