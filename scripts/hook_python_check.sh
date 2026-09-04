#!/usr/bin/env bash
# PostToolUse hook: deterministic validation after a Python edit (§46).
# - py_compile: hard failure (exit 2) on a syntax error — unambiguous breakage.
# - ruff: advisory — findings are printed as context; the full gate is `make check` / CI.
# Reads the hook JSON payload on stdin.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
RUFF="$ROOT/.venv/bin/ruff"

payload="$(cat)"
file_path="$(printf '%s' "$payload" | "${PY:-python3}" -c 'import json,sys;
try:
    d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path",""))
except Exception:
    print("")' 2>/dev/null)"

case "$file_path" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file_path" ] || exit 0

if [ -x "$PY" ]; then
  if ! err="$("$PY" -m py_compile "$file_path" 2>&1)"; then
    echo "py_compile FAILED for $file_path:" >&2
    echo "$err" >&2
    exit 2
  fi
fi

if [ -x "$RUFF" ]; then
  "$RUFF" check "$file_path" || echo "(ruff findings above are advisory — run 'make lint' for the full gate)"
fi
exit 0
