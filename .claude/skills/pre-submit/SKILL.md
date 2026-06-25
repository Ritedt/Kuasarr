---
name: pre-submit
description: Run Kuasarr's documented pre-PR checks before opening a pull request — Python syntax check, pytest, WebUI build, hostname/secret leak scan, docs-sync check, and API-contract check. Use before submitting work. Invoked via /pre-submit.
disable-model-invocation: true
---

# Pre-submit checks for Kuasarr

Run these before opening a PR (per `AGENTS.md`: "run the documented checks before submitting work"). Report a Go / No-Go per check. **Do NOT auto-commit or push.**

## Checks

1. **Python syntax** — `python3 -m py_compile` on every changed `.py` file (find them with `git --no-pager diff --name-only`).
2. **Tests** — `python3 -m pytest -q`. (Note: `tests/` is gitignored locally, but pytest runs them when present in the working tree.)
3. **WebUI build** — only if `kuasarr/webui/` changed: `cd kuasarr/webui && npm run build` (runs `tsc -b && vite build`). Must succeed with no TS errors — the built `dist/` is what Python serves.
4. **Hostname / secret leak scan** — scan staged/working changes for source hostnames and secrets:
   - `git --no-pager diff` must not reference `.claude/.secrets/`, real source URLs, or API keys.
   - If `.claude/.secrets/known_hostnames.txt` exists, grep the diff against each listed hostname.
5. **Docs sync** — per Documentation-First: if behavior/workflow/conventions changed, the matching `docs/` file must be updated. Flag missing doc updates.
6. **API contract** — if `kuasarr/api/` changed, confirm Newznab (`t=`) and SABnzbd (`mode=`) response shapes are unchanged (hand off to the `newznab-contract-reviewer` subagent for a deep check).
7. **Version discipline** — confirm `version.json` was NOT hand-edited; the version source of truth is `Hier_Version_Ändern.txt`.

## Output

A short report: one line per check with ✅/❌ and the exact command to fix any failure. End with an overall Go / No-Go.
