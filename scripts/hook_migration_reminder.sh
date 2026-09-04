#!/usr/bin/env bash
# PostToolUse hook: when an ORM model changes, remind that a migration is required (§46, CLAUDE.md rule 7).
set -u
payload="$(cat)"
file_path="$(printf '%s' "$payload" | python3 -c 'import json,sys;
try:
    d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path",""))
except Exception:
    print("")' 2>/dev/null)"

case "$file_path" in
  */intelligence/models/*.py)
    echo "NOTE: $(basename "$file_path") changed under intelligence/models/." >&2
    echo "      A schema change requires an Alembic migration: make revision m=\"...\" && make migrate" >&2
    echo "      (advisory; does not block)" >&2
    ;;
esac
exit 0
