#!/usr/bin/env bash
# PostToolUse hook: deterministic validation after a frontend edit (§46).
# Advisory eslint on the changed file. The hard gate is `npm run build` + `tsc --noEmit`
# in CI / Wave 9. No-op until apps/web has dependencies installed.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB="$ROOT/apps/web"

payload="$(cat)"
file_path="$(printf '%s' "$payload" | python3 -c 'import json,sys;
try:
    d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path",""))
except Exception:
    print("")' 2>/dev/null)"

case "$file_path" in
  "$WEB"/*.ts|"$WEB"/*.tsx|"$WEB"/*.js|"$WEB"/*.jsx) ;;
  *) exit 0 ;;
esac
[ -d "$WEB/node_modules" ] || exit 0
[ -f "$file_path" ] || exit 0

( cd "$WEB" && npx --no-install eslint "$file_path" ) \
  || echo "(eslint findings above are advisory — run 'npm run build' for the full gate)"
exit 0
