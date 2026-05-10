# claude-sidecar-monitor

<!-- ci-badges -->
[![CI](https://github.com/hankholcomb/claude-sidecar-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/hankholcomb/claude-sidecar-monitor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-0.1.0--rc1-blue.svg)](CHANGELOG.md)

> macOS-resident observability dashboard for Claude Code agent sessions. Glance from your phone: what's running, what's hung, where are tokens going.

<!-- T23-hero-screenshot -->
<!-- T22-install-gif -->

## Why I built this

I run Claude Code agents (often spawned by Augment Intent) on my Mac. Once I walk away from the keyboard, long-running agents are a black box. `csm` is the phone-glance dashboard I wanted: live agent state, hang detection with phone push, full transcripts for after-the-fact debugging, and a tree view that shows where tokens are going across a coordinator and its subagents.

It's local-only. The data sources are Claude Code's lifecycle hooks (HTTP-POSTed to a local FastAPI collector) and the JSONL transcripts in `~/.claude/projects/`. No Anthropic Admin API, no cloud, no telemetry leaving your Mac. Tailscale Serve makes the dashboard reachable from your phone over your tailnet without exposing a public endpoint.

## Quickstart

```bash
# 1. One-time prerequisites
brew install sqlcipher
curl -LsSf https://astral.sh/uv/install.sh | sh   # installs uv

# 2. Install csm
uv tool install git+https://github.com/hankholcomb/claude-sidecar-monitor#subdirectory=packages/collector

# 3. Bootstrap (prompts for passphrase, installs hooks + launchd, opens dashboard)
csm install

# 4. Set up Tailscale Serve so your phone can reach the dashboard
./scripts/tailscale-serve.sh

# 5. On your phone: open https://<mac>.<tailnet>.ts.net/ → "Add to Home Screen"
```

Total time: <5 minutes on a fresh Mac.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  macOS host                                                         │
│                                                                     │
│  shell / IDE / Intent ──spawns──▶ claude (Claude Code CLI)          │
│                                │                                    │
│                  hook POSTs    │   JSONL writes                     │
│                                ▼                                    │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ csm collector (launchd-managed FastAPI, port 8765)             │ │
│  │  • Hook receiver  • JSONL watcher  • Hang scanner              │ │
│  │  • Token aggregator  • Tree builder                            │ │
│  │  • SQLCipher store  • SSE + REST  • ntfy dispatcher            │ │
│  │  • Static React PWA at /                                       │ │
│  └────────────────────┬───────────────────────────────────────────┘ │
│                       │ Tailscale Serve (tailnet HTTPS)             │
└───────────────────────┼─────────────────────────────────────────────┘
                        ▼
                📱 iPhone → Add to Home Screen
                React PWA: live · tree · transcripts · tokens · settings
```

See [`docs/architecture.md`](docs/architecture.md) for sequence diagrams and the data model.

## Features

- **Live agent list** updates within 2 s of session start.
- **Hang detection**: yellow at 60s of silence, red at 180s, ntfy push at red.
- **Per-agent token totals** (input / output / cache_read / cache_write) update within 5 s of an assistant response.
- **Agent tree** for multi-implementor sessions, showing each node's tokens and parent-rollup totals.
- **Full transcripts** with diff-highlighted tool I/O.
- **At-rest encryption** (SQLCipher + Argon2id; key in macOS Keychain). Rotate the passphrase with `csm change-passphrase`.
- **Mobile-first PWA**: dark theme, custom icon, standalone mode, SSE-driven live updates.

## Token data caveat

Token counts come from the `usage` block in Claude Code's JSONL transcript files (per assistant turn). They reflect what the API reports at message time. Numbers may differ from your monthly Anthropic billing surface due to retries, cache pricing multipliers, and account-level aggregation. `csm` shows what the agent actually used; treat as accurate-to-the-message but indicative for billing.

## Troubleshooting

### Hooks aren't firing

Run `csm doctor --gate-test`. It writes a temporary log hook, runs `claude -p "echo ok"`, and confirms the receiver got a `SessionStart`. If it didn't, check:

1. `~/.claude/settings.json` contains the `csm-hook.sh` entries (re-run `csm install-hooks`).
2. The collector is running: `launchctl list | grep claude-sidecar` and `curl http://127.0.0.1:8765/healthz`.
3. Your `claude` invocation isn't passing `--setting-sources=` without `user`. Hook config lives in user settings.

### Dashboard unreachable from phone

```bash
tailscale serve status   # is it bound to :443?
csm doctor               # does it report Tailscale reachable?
```

LAN fallback: `http://<mac-local-ip>:8765/` works if you trust your Wi-Fi.

### ntfy not delivering

```bash
csm doctor               # is ntfy_topic set?
```

Test from the Settings page → "Test notification". If your phone has the ntfy app installed and is subscribed to the topic, you should see the push within ~5 s.

### Forgot the passphrase

`csm purge --reset-passphrase` wipes the database and re-initializes. The original data is unrecoverable — that's the point of the encryption.

## Roadmap

v0.1 ships the local single-Mac use case. Planned for v0.2+:

- Remote permission approval (the receiver shape is already v2-ready).
- Agent-team execution graphs.
- Retroactive cost analysis dashboard with Anthropic billing reconciliation.
- Multi-Mac aggregation.
- Linear / GitHub integration.

See [`docs/spec.md` §9](docs/spec.md#9-non-goals-deferred-to-v2) for the full non-goals list.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Conventional Commits enforced via Husky + commitlint.

## License

MIT — see [LICENSE](LICENSE).
