#!/usr/bin/env bash
set -euo pipefail

if command -v python3.11 >/dev/null 2>&1; then
  exec python3.11 "$@"
fi

if command -v pyenv >/dev/null 2>&1; then
  exec pyenv exec python3.11 "$@"
fi

echo "agent-monitor: python3.11 is required" >&2
exit 127
