#!/usr/bin/env bash
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZSHRC="${ZSHRC:-$HOME/.zshrc}"
TMUX_CONF="${TMUX_CONF:-$HOME/.tmux.conf}"
PYTHON_CMD=()

usage() {
  cat <<EOF
Usage: ./install.sh [--no-zsh] [--no-tmux]

Installs codex-tmux-sentinel by updating:
  $ZSHRC
  $TMUX_CONF

Environment overrides:
  ZSHRC=/path/to/zshrc TMUX_CONF=/path/to/tmux.conf ./install.sh
EOF
}

install_zsh=1
install_tmux=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-zsh)
      install_zsh=0
      ;;
    --no-tmux)
      install_tmux=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "install.sh: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

append_block() {
  local file="$1"
  local begin="$2"
  local end="$3"
  local content="$4"

  mkdir -p "$(dirname "$file")"
  touch "$file"

  if grep -Fq "$begin" "$file"; then
    "${PYTHON_CMD[@]}" - "$file" "$begin" "$end" "$content" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
begin = sys.argv[2]
end = sys.argv[3]
content = sys.argv[4]
text = path.read_text(encoding="utf-8")
lines = text.splitlines()
out = []
skipping = False
for line in lines:
    if line.strip() == begin:
        skipping = True
        continue
    if line.strip() == end:
        skipping = False
        continue
    if not skipping:
        out.append(line)
if content:
    out.append(content)
path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY
  else
    [[ -n "$content" ]] || return 0
    {
      printf '\n%s\n' "$content"
    } >> "$file"
  fi
}

if command -v python3.11 >/dev/null 2>&1; then
  PYTHON_CMD=(python3.11)
elif command -v pyenv >/dev/null 2>&1; then
  PYTHON_CMD=(pyenv exec python3.11)
else
  echo "install.sh: python3.11 or pyenv is required" >&2
  exit 1
fi

if [[ "$install_zsh" -eq 1 ]]; then
  zsh_begin="# codex-tmux-sentinel begin"
  zsh_end="# codex-tmux-sentinel end"
  zsh_block="$(cat <<EOF
$zsh_begin
export PATH="$PLUGIN_DIR/bin:\$PATH"

c() {
  local agent_id
  if [[ \$# -gt 0 && "\$1" != -* ]]; then
    agent_id="\$1"
    shift
  else
    agent_id="codex-\$(date +%Y%m%d-%H%M%S)"
  fi

  AGENT_ID="\$agent_id" AGENT_MONITOR_AGENT_ID="\$agent_id" agent-run "\$agent_id" codex "\$@"
}
$zsh_end
EOF
)"
  append_block "$ZSHRC" "# codex-tmux-monitor begin" "# codex-tmux-monitor end" ""
  append_block "$ZSHRC" "$zsh_begin" "$zsh_end" "$zsh_block"
  echo "Updated $ZSHRC"
fi

if [[ "$install_tmux" -eq 1 ]]; then
  tmux_begin="# codex-tmux-sentinel begin"
  tmux_end="# codex-tmux-sentinel end"
  tmux_block="$(cat <<EOF
$tmux_begin
set -g @agent_monitor_window_icons on
set -g @agent_monitor_auto_window_names on
set -g @agent_monitor_window_name_len 4
set -g @agent_monitor_refresh_interval 1
run-shell "$PLUGIN_DIR/agent-monitor.tmux"
$tmux_end
EOF
)"
  append_block "$TMUX_CONF" "# codex-tmux-monitor begin" "# codex-tmux-monitor end" ""
  append_block "$TMUX_CONF" "$tmux_begin" "$tmux_end" "$tmux_block"
  echo "Updated $TMUX_CONF"
fi

if [[ -n "${TMUX:-}" ]] && command -v tmux >/dev/null 2>&1; then
  tmux run-shell "$PLUGIN_DIR/agent-monitor.tmux" || true
  tmux refresh-client -S || true
  echo "Reloaded plugin in current tmux session"
fi

echo
echo "Done."
echo
echo "Next steps:"
if [[ "$install_zsh" -eq 1 ]]; then
  echo "  source \"$ZSHRC\""
  echo "  c"
else
  echo "  ensure $PLUGIN_DIR/bin is on PATH"
fi
if [[ "$install_tmux" -eq 1 ]]; then
  echo "  tmux source-file \"$TMUX_CONF\""
fi
echo
echo "Verify:"
echo "  $PLUGIN_DIR/scripts/python.sh $PLUGIN_DIR/scripts/agent_monitor.py list"
