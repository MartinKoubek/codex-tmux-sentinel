#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${TMUX:-}" ]] && command -v tmux >/dev/null 2>&1; then
  export AGENT_MONITOR_WINDOW_NAME_LEN="${AGENT_MONITOR_WINDOW_NAME_LEN:-$(tmux show-option -gqv @agent_monitor_window_name_len 2>/dev/null || true)}"
fi

"$SCRIPT_DIR/window-name.sh" >/dev/null 2>&1 || true
printf ''
