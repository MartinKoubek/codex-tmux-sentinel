# Repository Guidelines

## Project Structure & Module Organization

This repository is a tmux plugin for displaying Codex activity per window.

- `agent-monitor.tmux`: tmux plugin entrypoint and option wiring.
- `scripts/`: implementation scripts.
  - `agent_monitor.py`: locked state file, activity inference, and icon rendering.
  - `agent-run`, `agent-status`: user-facing command implementations.
  - `window-status.sh`, `window-name.sh`, `statusbar.sh`: tmux integration helpers.
  - `python.sh`: Python 3.11 launcher.
- `bin/`: PATH-friendly shims for `agent-run` and `agent-status`.
- `screenshots/`: README SVG previews.
- `install.sh`: installer for shell and tmux config.

There is no separate test directory currently; use command-level verification.

## Build, Test, and Development Commands

Use Python 3.11 for all Python commands.

```bash
zsh -n install.sh agent-monitor.tmux scripts/*
```
Checks shell/tmux script syntax.

```bash
./scripts/python.sh -m py_compile scripts/agent_monitor.py
```
Checks Python syntax.

```bash
AGENT_MONITOR_HOME=/tmp/sentinel-test scripts/agent-run demo true
AGENT_MONITOR_HOME=/tmp/sentinel-test scripts/python.sh scripts/agent_monitor.py list
```
Smoke-tests state registration and listing without touching real state.

```bash
tmux run-shell "$PWD/agent-monitor.tmux"
```
Reloads the plugin in the current tmux session.

## Coding Style & Naming Conventions

Shell scripts use Bash with `set -euo pipefail`. Keep scripts small and command-focused. Python code should stay standard-library only, type-annotated where useful, and compatible with Python 3.11. Prefer explicit state names: `IDLE`, `BUSY`, `NEEDS_HUMAN`, `FAILED`, `STALLED`.

Use lowercase hyphenated file names for shell scripts and snake_case for Python functions.

## Testing Guidelines

No formal test framework is configured. Before committing, run the syntax checks above and at least one isolated `AGENT_MONITOR_HOME=/tmp/...` smoke test. For tmux display changes, verify `scripts/window-status.sh <window-id> <window-name>` and refresh tmux with `tmux refresh-client -S`.

## Commit & Pull Request Guidelines

The history uses short imperative commit messages, for example `Clean up stale Codex hook config`. Keep commits focused and explain user-visible behavior changes in the body when needed.

Pull requests should include a concise summary, manual verification commands, and screenshots when display output changes. Mention any changes to installer behavior or user config files such as `~/.zshrc`, `~/.tmux.conf`, or `~/.codex/config.toml`.

## Security & Configuration Tips

Do not commit local IDE files, Codex session data, or user-specific monitor state. The installer writes managed blocks to shell/tmux config; keep those blocks idempotent and clearly marked. Use `/tmp` state directories for tests to avoid mutating `~/.agent-monitor`.
