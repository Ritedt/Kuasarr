#!/usr/bin/env bash
# PreToolUse guard for `git commit` — blocks accidental commits of secrets / source hostnames.
# Called by Claude Code PreToolUse hook (matcher: Bash). Reads the tool-call JSON from stdin.
# Exit 2 = block the tool call in Claude Code; 0 = allow.
#
# Project rule (AGENTS.md): API keys, kuasarr.ini, and source hostnames must NEVER be committed.
# The known-hostname list is optional and gitignored (local only): .claude/.secrets/known_hostnames.txt
set -uo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); print(d.get("tool_input",{}).get("command",""))
except Exception:
    print("")' 2>/dev/null)"

# Only act on commits
case "$cmd" in
  *git\ commit*|*"git commit"*) : ;;
  *) exit 0 ;;
esac

# 1) Block staging anything under .claude/.secrets/ (API keys)
if git diff --cached --name-only 2>/dev/null | grep -qE '^\.claude/\.secrets(/|$)'; then
  echo "BLOCKED (commit): staging files under .claude/.secrets/ is forbidden (API keys)." >&2
  exit 2
fi

# 2) Block high-signal secret patterns in added lines
if git diff --cached -U0 2>/dev/null | grep -E '^\+' | grep -qiE '(api[_-]?key|apikey|secret|token|password|passwd|pwd|authtoken)[[:space:]]*[=:][[:space:]]*["'"'"'][A-Za-z0-9._\-]{16,}'; then
  echo "BLOCKED (commit): staged diff contains a likely secret (key/token/password)." >&2
  echo "Move the value to ENV/kuasarr.ini — never commit it." >&2
  exit 2
fi

# 3) Optional: known source hostnames (gitignored, local only)
known=".claude/.secrets/known_hostnames.txt"
if [ -f "$known" ]; then
  while IFS= read -r host || [ -n "$host" ]; do
    case "$host" in ''|'#'*) continue ;; esac
    # host is used as a fixed string in the grep pattern
    if git diff --cached 2>/dev/null | grep -qF -- "+${host}"; then
      echo "BLOCKED (commit): staged diff references known source hostname '${host}'." >&2
      echo "Per AGENTS.md hostnames must never be committed." >&2
      exit 2
    fi
  done < "$known"
fi

exit 0
