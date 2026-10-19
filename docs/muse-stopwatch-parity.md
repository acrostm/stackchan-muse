# Muse StopWatch parity

MuseStack reuses the useful design patterns from the user's `muse-stopwatch`
adapter without importing its board-specific display or audio code.

| StopWatch behavior | MuseStack integration |
|---|---|
| More than two seconds held before upload | `muse_ptt_guard` records physical press/release time; every press has a bounded turn id so a later press cannot overwrite the prior recording's release or cancel state |
| Short/cancelled recordings never retry | short presses cancel the turn and discard the PSRAM note; allocation failure never falls back to live upload |
| Browser Wi-Fi setup with persistent PIN | local `Muse-Setup-XXXXXX` AP, eight-digit NVS PIN, CSRF token and same-subnet checks |
| Secrets survive blank fields | setup page never reads back credentials; empty secret fields preserve saved values |
| Per-SSID SOCKS5/clash routing | `sw_proxy` wraps only `muse.ai`/`metaaivm.com`; profiles are bounded, network-scoped and validate private IPv4 proxy hosts |
| Doubao configuration and preview | direct device synthesis worker with cancellation, generation checks, bounded output, cached HTTP body draining and WAV browser preview |
| Generation cancellation | cancelled synthesis cannot be adopted by the next request or the next dialogue turn |
| Real event notifications | idle final Muse messages enter a bounded, deduplicated inbox; the voice task wakes, chirps, TTS-reads and captions them |

Differences are intentional: StackChan has no yellow auxiliary button, so a
short tap on its talk control is rejected; later hardware work may bind a head
pat to cancellation. StackChan also retains its dedicated servo calibration and
arbitration model rather than copying StopWatch motion code.

Server delivery of every phone message and scheduled-task result is not yet
proven. The notification inbox only accepts terminal assistant/text events and
is deliberately bounded; it does not replay a burst of stale history after a
reconnect.
