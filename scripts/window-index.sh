#!/usr/bin/env bash
set -euo pipefail

index="${1:-}"
out=""

for ((i = 0; i < ${#index}; i++)); do
  char="${index:i:1}"
  case "$char" in
    0) out+="𝟎" ;;
    1) out+="𝟏" ;;
    2) out+="𝟐" ;;
    3) out+="𝟑" ;;
    4) out+="𝟒" ;;
    5) out+="𝟓" ;;
    6) out+="𝟔" ;;
    7) out+="𝟕" ;;
    8) out+="𝟖" ;;
    9) out+="𝟗" ;;
    *) out+="$char" ;;
  esac
done

printf '%s' "$out"
