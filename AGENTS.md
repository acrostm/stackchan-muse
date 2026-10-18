# MuseStack engineering rules

Use Chinese for user-facing work. Read the applicable upstream instructions in
`firmware/esp32/AGENTS.md` before modifying firmware. Never push directly to main,
disable its protections, fabricate bot approvals, or bypass failed CI. Use a PR.

Do not commit account tokens, recordings, factory images, device identities or
account-enabled binaries. Do not flash until the requested checks and backup
requirements are met. Preserve the distinction between compiled, simulated and
hardware-verified behavior.

## Code Review Rules

### Account and hardware boundaries

Reject changes that leak credentials or allow old speech/motion from a cancelled
turn to resume. Motion must pass calibration, limits, speed control and a single
arbiter. An HTTP success is not evidence that audio played or that Muse completed
a task. Flag release claims without matching hardware evidence.

### Merge controls

Reject changes that weaken the current-commit Codex gate, accept an untrusted
actor, accept a stale review, treat a reaction or generic comment as approval,
or execute PR code with a writable review token.

### Explicit verdict for the official Codex GitHub reviewer

When reviewing a PR, after reviewing its actual diff and applicable rules, give
an explicit verdict in the standard GitHub review body. If there are no findings
and you approve, include exactly one line `MuseStack-Review: APPROVE <HEAD_SHA>`
with the full actual 40-character PR head SHA. If there are findings, missing
context or unfinished review, do not emit that line. The line represents your
review conclusion; it is not permission to waive CI or hardware acceptance.
