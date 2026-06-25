---
name: add-source
description: Scaffold a new DDL source for Kuasarr following the existing NK/DW/SJ pattern — a search source (kuasarr/search/sources/XX.py) plus a download source (kuasarr/downloads/sources/XX.py), each exposing a `Source` class. Sources auto-register via pkgutil discovery. Use when adding support for a new source.
---

# Add a new Kuasarr source

Use this skill to add a new DDL source (two-letter uppercase identifier, e.g. `NK`, `DW`, `SJ`) following the established pattern. **Sources auto-register** — there is no manual registry to edit.

## CRITICAL — never commit hostnames or URLs

Per `AGENTS.md`, source hostnames/URLs must NEVER appear in any file that is not gitignored. Keep real hostnames in the runtime config (`kuasarr.ini`) / env only. In code, reference the source by its `initials` (e.g. `"nk"`) and read the configured hostname from settings at runtime — copy exactly how existing sources do it (see `hostname = "nk"` style identifiers, which are just the id, not the real URL).

## What a source is

A source is a pair of modules, auto-discovered by filename via `pkgutil.iter_modules` in `search/sources/__init__.py` and `downloads/sources/__init__.py`:

| Layer | Path | Base class | Purpose |
|-------|------|------------|---------|
| Search | `kuasarr/search/sources/XX.py` | `kuasarr.search.base.AbstractSearchSource` | Search listings → RSS items for the Newznab response |
| Download | `kuasarr/downloads/sources/XX.py` | `kuasarr.downloads.base.AbstractDownloadSource` | Resolve a release URL → decrypted download links |

`XX` = lowercase module name (e.g. `nk.py`). Both classes MUST be named `Source` and expose an `initials` attribute (the 2-letter id). Modules starting with `_` are skipped by discovery.

## Steps

1. **Read the base contracts** — `kuasarr/search/base.py` and `kuasarr/downloads/base.py` to learn the required methods/attributes (`initials`, search/resolve methods, return shapes).
2. **Pick a template** — copy the closest existing source:
   - `nk.py` — simple HTML scrape + mirrors (`supported_mirrors`).
   - `sj.py` — credential + reCAPTCHA session under `kuasarr/providers/sessions/`.
3. **Create the search source** at `kuasarr/search/sources/<initials>.py`:
   - `class Source(AbstractSearchSource)` with `initials = "xx"`.
   - Implement search/listing → Newznab/RSS-shaped items.
   - Reuse helpers: `kuasarr.providers.imdb_metadata.get_localized_title`, `kuasarr.providers.log.{info,debug}`, `BeautifulSoup`, `requests`.
4. **Create the download source** at `kuasarr/downloads/sources/<initials>.py`:
   - `class Source(AbstractDownloadSource)` with matching `initials`.
   - Resolve release page → decrypt captcha-protected links (see `kuasarr/downloads/linkcrypters/`, e.g. `filecrypt.py`, `keeplinks.py`).
   - If login/captcha is needed, add a session helper under `kuasarr/providers/sessions/<initials>.py` (mirror `sj.py`).
5. **Categorization** — check `kuasarr/categories/` to map releases to Newznab categories; add a mapping if missing.
6. **Verify** — `python3 -m py_compile` both files, then run `python3 -m pytest`. Confirm the source is discovered (its `initials` appears in `get_sources()` keys).
7. **Docs** — per Documentation-First (`AGENTS.md`), update `docs/` to describe the new source (behavior/workflow). Do NOT put the hostname in docs.

## Don't

- No hardcoded hostnames/URLs — config only.
- Don't edit the `__init__.py` registries (auto-discovered).
- Keep the commit delta minimal — only the two modules (+ session/categories files if needed).
- This is NOT a torrent/usenet client — never add NZB/torrent/magnet handling.
