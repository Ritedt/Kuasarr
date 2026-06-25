# Quasarr-Upstream-Integration — Master-Plan

> Konzept-Adaption von `rix1337/Quasarr` (Upstream) in Kuasarr (Fork seit v1.12.3, ~80 PRs entfernt).
> **Prinzip: KEIN Copy-Paste** — Kuasarr hat eine eigene Architektur (Registry-basierte Suche via `AbstractSearchSource`, React-WebUI, String-ID-Kategorien intern). Nur Konzepte werden adaptiert.

## Phasen

| Phase | Branch / PR | Items | Aufwand |
|-------|-------------|-------|---------|
| **1 — Kern-Hebel** | `feat/v2.1-imdb-tier-searchcache-nzb-escape` (#64) | P1-A 3-Tier-IMDb · P1-B SearchCache · P1-C NZB-escape | ~2,5 Wo |
| **2 — Performance** | `feat/v2.1-search-deadline-xrel-parallel` (#65) | P2-A Search-Deadline+max_workers · P2-B xREL-Parallel+Caching · P2-C Stale-Cache | ~1,5 Wo |
| **3 — *arr + Stabilität** | `feat/v2.1-arr-wanted-dedupe-delete` (#66) | P3-A Wanted-List-Seeding · P3-B Dedupe · P3-C idempotenter Delete | ~2 Wo |
| **4 — Bugfixes + Optional** | `feat/v2.1-fx-fix-dynamic-caps` (#67) | P4-A FX-per-entry · P4-B dynamische caps · P4-C OMDb/TMDB (optional) · P4-D flaresolverr-next-Doku | ~2,5 Wo |

**Gesamt:** ~13 Personenwochen. Phase 1 parallelisierbar (3 Entwickler → ~1 Woche).

## Phase 1 — Detail

- **P1-A [HIGH] 3-Tier-IMDb-Kette** — `kuasarr/providers/imdb_metadata_api.py` (neu): `IMDbAPIAPI` (api.imdbapi.dev: `/titles/{id}` + `/akas`, de-AKA via `country.code=='de'`) + `IMDbCDN` (v2.sg.media-imdb.com/suggestion). In `get_localized_title` (`imdb_metadata.py:111`) VOR HTML/FlareSolverr-Pfad API-Tier probieren; in `get_imdb_id_from_title` (`:190`) API/CDN-Suche als erste Stufe. **Löst das AWS-WAF-Problem ohne API-Keys.**
- **P1-B [HIGH] SearchCache** — `kuasarr/search/cache.py` (neu): thread-safe `SearchCache` (Lock+dict+(value,expiry), Cleanup alle 60s). Cache-Key aus `(source.initials, mode, imdb_id, phrase, season, ep, mirror)` — **`source.initials` muss per Default-Arg eingefroren werden** (Closure-Bug!). Integration in `search/__init__.py` vor `ThreadPoolExecutor` (`:256`). TTL 300s (imdb/phrase), 60s (feed), 30s (leere []).
- **P1-C [HIGH] Fake-NZB-Attribut-Escaping** — `_xml_attr`-Helper (`sax_utils.quoteattr`) in `api/arr/__init__.py`; `fake_nzb_file` (`:27-36`): `title/url/mirror/password/imdb_id` escapen, `size_mb` numerisch lassen.

## Harte Abhängigkeiten

- **P2-A MUSS nach P1-B** — sonst verwirft der Deadline gecachte 0ms-Treffer
- **P2-A vor P2-B** spezifizieren (xREL unter globalem Deadline)
- **Geteilte Stelle `get_search_results`** (`search/__init__.py:108-289`): P1-B, P2-A, P3-A, P3-B greifen dort an → serielles Merge
- `delete_package` liegt in `downloads/packages/__init__.py:557` (nicht `packages.py`)

## Branch/PR-Strategie

- **Frische Branches von `main`** — NICHT auf `fix/imdb-title-extraction` (PR #63 offen!)
- **Ein PR pro Phase**, logische Commits, **kein Squash** (git-bisect-freundlich)
- Commit-Messages: `Co-Authored-By: Claude <noreply@anthropic.com>`; PR-Bodies: `Generated with Claude Code`

## Test-Strategie

Pro Item: **cat-Test** (python-Snippet, online) + **Unit-Test** (pytest, offline, Fixtures) + **Integration** + **E2E via `arr`-Skill** (Radarr 192.168.178.12:7878, Sonarr 192.168.178.6:8989). Merge-Voraussetzung: Indexer bleibt `enabled`, keine neuen Rejects, manuelle WebUI-Suche gegen ≥1 Hostname.

## Risiko-Register (Top)

- `api.imdbapi.dev` kostenlos **ohne SLA** → MUSS sauber `None`+fallen-through; bei >20% Ausfall → P4-C (TMDB)
- CDN-Endpoint inoffiziell/unstable → nur Redundanz, kurze Timeouts (5s)
- Lambda-Closure-Bug (P1-B): `source.initials` einfrieren
- Race-Condition xREL-Cache (P2-B): nicht thread-safe → Lock
- *arr unkonfiguriert (P3-A): MUSS still `[]` liefern (Feed darf nicht blockieren)
- ID-Kollision dynamische caps (P4-B): `docs`+`books` → beide 7000 → dedup vor Join

## Vorgehen

1. `imdb_metadata.py`-WIP sichern (vor Branch-Erstellung)
2. Branch `feat/v2.1-imdb-tier-searchcache-nzb-escape` von `origin/main`
3. Phase 1 implementieren (P1-A, P1-B, P1-C) + adversarieller Code-Review
4. cat-Tests + arr-Skill-E2E + Commit + PR #64
