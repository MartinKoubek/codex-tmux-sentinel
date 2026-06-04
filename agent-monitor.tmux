#!/usr/bin/env bash
set -euo pipefail

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bold_window_index_format() {
  local format="$1"
  local index_command="#($CURRENT_DIR/scripts/window-index.sh '#I')"
  if [[ "$format" == *"#I"* && "$format" != *"scripts/window-index.sh"* ]]; then
    printf '%s' "${format//#I/$index_command}"
  else
    printf '%s' "$format"
  fi
}

tmux set-option -gq @agent_monitor_plugin_dir "$CURRENT_DIR"

if [[ -z "$(tmux show-option -gqv @agent_monitor_home)" ]]; then
  tmux set-option -gq @agent_monitor_home "$HOME/.agent-monitor"
fi

if [[ -z "$(tmux show-option -gqv @agent_monitor_stall_timeout)" ]]; then
  tmux set-option -gq @agent_monitor_stall_timeout "600"
fi

if [[ -z "$(tmux show-option -gqv @agent_monitor_window_icons)" ]]; then
  tmux set-option -gq @agent_monitor_window_icons "on"
fi

if [[ -z "$(tmux show-option -gqv @agent_monitor_auto_window_names)" ]]; then
  tmux set-option -gq @agent_monitor_auto_window_names "on"
fi

if [[ -z "$(tmux show-option -gqv @agent_monitor_window_name_len)" ]]; then
  tmux set-option -gq @agent_monitor_window_name_len "4"
fi

if [[ -z "$(tmux show-option -gqv @agent_monitor_refresh_interval)" ]]; then
  tmux set-option -gq @agent_monitor_refresh_interval "1"
fi

refresh_interval="$(tmux show-option -gqv @agent_monitor_refresh_interval)"
if [[ "$refresh_interval" =~ ^[0-9]+$ ]] && [[ "$refresh_interval" -gt 0 ]]; then
  current_status_interval="$(tmux show-option -gqv status-interval)"
  if [[ ! "$current_status_interval" =~ ^[0-9]+$ ]] || [[ "$current_status_interval" -eq 0 ]] || [[ "$current_status_interval" -gt "$refresh_interval" ]]; then
    tmux set-option -gq status-interval "$refresh_interval"
  fi
fi

if [[ "$(tmux show-option -gqv @agent_monitor_auto_window_names)" != "off" ]]; then
  rename_command="AGENT_MONITOR_WINDOW_NAME_LEN='#{@agent_monitor_window_name_len}' '$CURRENT_DIR/scripts/window-name.sh'"
  tmux set-hook -gq pane-focus-in "run-shell \"$rename_command\"" || true
  tmux set-hook -gq pane-current-path-changed "run-shell \"$rename_command\"" || true
  tmux set-hook -gq after-new-window "run-shell \"$rename_command\"" || true
  tmux run-shell "$rename_command" || true
fi

if [[ "$(tmux show-option -gqv @agent_monitor_window_icons)" != "off" ]]; then
  if [[ -z "$(tmux show-option -gqv @agent_monitor_original_window_status_format)" ]]; then
    tmux set-option -gq @agent_monitor_original_window_status_format "$(tmux show-option -gqv window-status-format)"
  fi

  if [[ -z "$(tmux show-option -gqv @agent_monitor_original_window_status_current_format)" ]]; then
    tmux set-option -gq @agent_monitor_original_window_status_current_format "$(tmux show-option -gqv window-status-current-format)"
  fi

  window_status_format="$(tmux show-option -gqv @agent_monitor_original_window_status_format)"
  window_status_current_format="$(tmux show-option -gqv @agent_monitor_original_window_status_current_format)"
  window_status_format="$(bold_window_index_format "$window_status_format")"
  window_status_current_format="$(bold_window_index_format "$window_status_current_format")"
  window_status_icon="#($CURRENT_DIR/scripts/window-status.sh '#{window_id}' '#{window_name}')"

  tmux set-option -gq window-status-format "$window_status_format $window_status_icon"
  tmux set-option -gq window-status-current-format "$window_status_current_format $window_status_icon"
fi

if [[ "$(tmux show-option -gqv @agent_monitor_auto_window_names)" != "off" ]]; then
  status_right="$(tmux show-option -gqv status-right)"
  case "$status_right" in
    *"$CURRENT_DIR/scripts/statusbar.sh"*)
      ;;
    *)
      tmux set-option -g status-right "#($CURRENT_DIR/scripts/statusbar.sh) $status_right"
      ;;
  esac
fi
