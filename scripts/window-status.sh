#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
window_id="${1:-}"
window_name="${2:-}"

if [[ -n "${TMUX:-}" ]] && command -v tmux >/dev/null 2>&1; then
  export AGENT_MONITOR_HOME="${AGENT_MONITOR_HOME:-$(tmux show-option -gqv @agent_monitor_home 2>/dev/null || true)}"
  export AGENT_MONITOR_STALL_TIMEOUT="${AGENT_MONITOR_STALL_TIMEOUT:-$(tmux show-option -gqv @agent_monitor_stall_timeout 2>/dev/null || true)}"
fi

"$SCRIPT_DIR/python.sh" "$SCRIPT_DIR/agent_monitor.py" window-status --window-id "$window_id" --window "$window_name"
