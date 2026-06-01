#!/usr/bin/env bash
set -euo pipefail

COMMON_NAMES="${AGENT_MONITOR_COMMON_PATH_NAMES:-source,src,lib,common,app,apps,packages,pkg,bin,build,dist,node_modules,vendor,public,private,tmp,temp,test,tests,spec,specs,docs,doc,config,configs,scripts,script}"
NAME_LEN="${AGENT_MONITOR_WINDOW_NAME_LEN:-4}"

is_common_name() {
  local name="$1"
  local item
  IFS=',' read -r -a names <<< "$COMMON_NAMES"
  for item in "${names[@]}"; do
    if [[ "$name" == "$item" ]]; then
      return 0
    fi
  done
  return 1
}

valuable_name() {
  local path="${1%/}"
  local name=""

  while [[ -n "$path" && "$path" != "/" ]]; do
    name="${path##*/}"
    if [[ -n "$name" && "$name" != .* ]] && ! is_common_name "$name"; then
      printf '%s\n' "${name:0:NAME_LEN}"
      return 0
    fi
    path="${path%/*}"
  done

  if [[ -n "$name" ]]; then
    printf '%s\n' "${name:0:NAME_LEN}"
  fi
}

if [[ -z "${TMUX:-}" ]] || ! command -v tmux >/dev/null 2>&1; then
  exit 0
fi

while IFS=$'\t' read -r window_id current_name; do
  [[ -n "$window_id" ]] || continue
  first_path="$(tmux list-panes -t "$window_id" -F '#{pane_index}	#{pane_current_path}' 2>/dev/null | sort -n | awk -F '\t' 'NR == 1 { print $2 }')"
  [[ -n "$first_path" ]] || continue
  new_name="$(valuable_name "$first_path")"
  [[ -n "$new_name" ]] || continue
  [[ "$current_name" == "$new_name" ]] && continue
  tmux rename-window -t "$window_id" "$new_name" 2>/dev/null || true
done < <(
  tmux list-windows -a -F '#{window_id}	#{window_name}' 2>/dev/null
)
