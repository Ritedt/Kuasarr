#!/usr/bin/env bash
# PreToolUse guard for Edit/Write/MultiEdit — blocks direct edits to version.json.
# The version source of truth is Hier_Version_Ändern.txt; CI propagates to version.json.
# Exit 2 = block the tool call in Claude Code; 0 = allow.
set -uo pipefail

input="$(cat)"
path="$(printf '%s' "$input" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin)
    ti=d.get("tool_input",{})
    p=ti.get("file_path") or ti.get("notebook_path") or ""
    print(p if isinstance(p,str) else "")
except Exception:
    print("")' 2>/dev/null)"

case "$path" in
  version.json|*/version.json)
    echo "BLOCKED: version.json must not be edited directly." >&2
    echo "Change the version in Hier_Version_Ändern.txt — CI propagates it." >&2
    exit 2
    ;;
esac
exit 0
