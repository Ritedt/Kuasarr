# Repository Guidelines

## Project Overview

Kuasarr connects JDownloader2 with Radarr, Sonarr, and LazyLibrarian. It also decrypts links protected by CAPTCHAs. The primary audience is users who want to run the *arr stack with JDownloader2 instead of a traditional usenet downloader while automating as much of the flow as possible.

Kuasarr acts as the bridge between the *arr apps and JDownloader2 by exposing itself as both a `Newznab Indexer` and a `SABnzbd client`. It is not a real usenet indexer, does not know what NZB files are, and should not be treated as one.

## Documentation First

Before formulating a plan or implementing a change, start with `docs/README.md`. It is the index for the documentation set and explains which documents exist and what each one covers.

The root `README.md` is meant to introduce the Kuasarr project to users. It is not the primary working reference for agents and should be ignored for planning and implementation unless the task explicitly asks for changes to `README.md` or asks about its content.

After checking `docs/README.md`, open the file in `docs/` that matches the task and use it as the source of truth. If the task spans multiple areas, read each relevant document first.

Any major change to Kuasarr must include the corresponding documentation updates described in this section. If the change affects behavior, workflows, conventions, architecture, or contributor expectations, update the matching file in `docs/`. If no document matches the topic, create or update one as part of the change before finalizing the work.

## Core Capabilities

Treat these as the first-class product goals:

- Connecting the *arr stack with JDownloader2
- Autonomously controlling JDownloader2 to support that integration
- Handling protected-link and anti-CAPTCHA mechanics so the workflow is as automated as possible
- Supporting DeathByCaptcha and 2Captcha for CAPTCHA solving
- Supporting related filtering, categorization, and notifications only when they strengthen the core automation flow

## Product Boundaries

The project focus is improving and maintaining the existing feature set. Automation for third-party tools and sources is effectively endless, so features outside the core capabilities are usually feature creep or bloat that steal time from maintaining compatibility with those third parties.

Do not propose or implement broad new abstractions, adjacent product ideas, or convenience features unless they directly support the core Kuasarr workflow.

This is NOT a torrent or usenet client. Never implement NZB parsing, torrent handling, or magnet link support.

## Change Discipline

Keep changes aligned with the existing `kuasarr/` package layout, prefer `pip` for local commands, and run the documented checks before submitting work. Keep commit subjects short and imperative, keep pull requests focused, and avoid bundling unrelated edits.

Do not change more code than necessary. Refactors should be proposed and explicitly requested, not performed opportunistically. Keep commit deltas low and avoid creating refactor overhead such as rewriting unrelated tests.

Unit tests should usually change only when the intended behavior in the covered area changed, or when the existing test is incorrect. Do not rewrite tests just because nearby code changed shape.

## Skill Execution

When a repo-local skill defines an explicit command, execute that command exactly as written unless the skill itself explicitly allows an alternative invocation.

Do not substitute a different shell, interpreter, wrapper, or platform-specific entrypoint just because it appears equivalent. If a local alias or shim is useful for one machine, keep that in user-specific agent configuration outside the repository.

If a skill command fails, inspect why it failed and discuss the best next step with the user before retrying with a different invocation, unless the skill itself defines a fallback.

## Security And Content Rules

Do not commit real credentials, `.env` files, API keys, or actual source hostnames. Use environment variables for all sensitive values in Docker deployments. Keep `kuasarr.ini` out of version control.

Never, at any point, add the hostnames of any sources Kuasarr supports to any file that is not gitignored.

Sensitive values (passwords, tokens, API keys) must never be hardcoded — always read from ENV or INI.

## The Two API Keys

Kuasarr recognizes **two** API credentials, and they are not interchangeable in spirit:

| Key | Stored in | Used by | Obtainable via |
| --- | --- | --- | --- |
| Master-Key | `Config('API')['key']` | Radarr, Sonarr, LazyLibrarian | printed on the console at first start |
| Browser-Token | `Config('WebUI')['api_token']` | the React WebUI only | `GET /api/key` |

`GET /api/key` deliberately returns the browser token, never the master key. A key lifted from a browser (devtools, a screenshot, an XSS) must not compromise the whole `*arr` integration — and that only holds because the browser token can be revoked on its own.

- `POST /regenerate-browser-token` replaces **only** `WebUI.api_token`. Radarr/Sonarr are unaffected. This is the button to reach for after an XSS in the SPA.
- `POST /regenerate-api-key` rotates the **master** key and, with it, the browser token. This breaks every `*arr` until they are reconfigured. Use it when the master key itself leaked.

Both are `POST` with `@require_csrf_token`; `GET /regenerate-api-key` used to exist and an `<img src=…>` was enough to rotate it. Both are reachable from the API-Settings block on the legacy `/` page, which carries the token as a hidden `csrf_token` field.

The browser token is accepted everywhere the master key is accepted; nothing rejects it server-side. The separation protects the master key, it is not a second permission level.

## API Response Contract

Every route under `/api/` answers with `{"data": <payload>}` on success. Failures are normalized centrally by `kuasarr/api/error_handler.py` into:

```json
{"error": {"code": "<stable-slug>", "message": "<human readable>"}}
```

The error shape always comes with a matching HTTP status (400/401/403/404/405/409/429/500/502). Returning HTTP 200 with `{"success": false}` is a bug: the client only throws on `!response.ok` and would silently render an empty page.

Two caveats on what the central handler does and does not cover. It normalizes **errors**; it cannot touch a handler that returns `200 {"success": false}` on purpose, because no exception is raised. The legacy routes `/api/notifications/{save,test/discord,test/telegram}` still do exactly that and are read as such by the legacy page's JavaScript — fix them only together with that page.

Some routes are shared with the legacy HTML pages, whose inline JavaScript branches on `data.success`. `/api/packages/{delete,pause,resume}` still answer `200 {"success": true}` for that reason, and the SPA ignores the body. Do not "normalize" those to `{"data": …}` without moving the legacy page to the new shape in the same change.

Routes outside `/api/` keep returning HTML, which the legacy pages (`/search`, `/packages`, `/captcha/...`) depend on; the handler emits a minimal escaped HTML error page for those instead of JSON.

## CSRF

`@require_csrf_token` compares `X-CSRF-Token` against the `kuasarr_csrf` cookie; the SPA obtains both from `GET /api/csrf`. `GET /regenerate-api-key` was changed to `POST` for the same reason — a `GET` that mutates state can be triggered by an `<img>` tag, with no way for the server to tell the request apart from a real one.

Currently guarded: `POST /api/categories`, `POST|DELETE /api/categories/<id>`, `POST /api/notifications`, `POST /api/notifications/test`, `POST /api/settings/core`, `POST /regenerate-api-key`.

**Open gap:** 25 of the 31 `/api` write routes are unguarded — `POST /api` (the *arr shim), `/api/search`, `/api/search/download`, `/api/packages/{delete,pause,resume}`, `/api/jdownloader/{config,save,verify}`, `/api/settings` and `/api/settings/*-config`, `/api/hosters/*`, `/api/hostnames`, `/api/dbc_credentials`, and the legacy `/api/notifications/{save,settings,test/discord,test/telegram}`. They still require the API key, which a cross-site form cannot supply, so they are not exploitable from a third-party page — but they are not double-submit protected either.

They are left unguarded deliberately, not overlooked. `POST /api` is the Newznab/SABnzbd shim and must keep working without a CSRF header. For the others the client is already ready: `fetchApi` in `kuasarr/webui/src/lib/api.ts` attaches `X-CSRF-Token` to every mutating call, so the decorator can be added without touching the frontend. Do that per route and verify the matching legacy caller still sends the header, rather than sweeping all 25 at once — `POST /api` must stay out of it.

## Terminology

When referring to integrations such as `NK` or `DW`, always call them `sources`.

Always abbreviate sources as two-letter uppercase identifiers, for example `NK`, `DW`, `DD`, or `SJ`.

## Multi-arch Compatibility

Maintain compatibility with `linux/amd64`, `linux/arm64`, and `linux/arm/v7`. Do not introduce amd64-only dependencies.

## Versioning

Version changes must only be made in `Hier_Version_Ändern.txt`. CI propagates the version to all other locations automatically.
