# Kuasarr — Claude Code Context

## Project Overview

Kuasarr is a Python-based fork of [quasarr](https://github.com/rix1337/quasarr) that bridges JDownloader 2 with Radarr, Sonarr, and LazyLibrarian. It emulates a Newznab indexer and SABnzbd client, scrapes DDL sites for download links, decrypts CAPTCHA-protected links, and dispatches jobs to JDownloader via My-JDownloader API. It does **not** handle NZB or torrent files.

## Tech Stack

* **Language**: Python 3 (99%+)
* **Web Framework**: Bottle (`bottle>=0.13.4`)
* **HTML Parsing**: BeautifulSoup4 (`beautifulsoup4>=4.14.2`)
* **HTTP**: requests + urllib3
* **Captcha**: deathbycaptcha-official, with 2Captcha support
* **Crypto**: pycryptodomex (for link decryption)
* **JS execution**: dukpy (inline JavaScript evaluation for obfuscated links)
* **Images/CAPTCHA preprocessing**: Pillow
* **Packaging**: pyproject.toml + setup.py + MANIFEST.in
* **Distribution**: Docker (GHCR: `ghcr.io/ritedt/kuasarr`), multi-arch (amd64, arm64, arm/v7)
* **Config**: `kuasarr.ini` (INI format), mounted at `/config/`
* **Versioning**: `version.json` (single source of truth)

## Repository Structure

```
Kuasarr/
├── kuasarr/           # Main application package
│   └── static/        # Web UI assets (logo, PWA manifest, etc.)
├── docs/              # Documentation
├── scripts/           # Helper / release scripts
├── .github/           # GitHub Actions workflows
├── Kuasarr.py         # Entrypoint
├── Dockerfile
├── requirements.txt
├── pyproject.toml
├── setup.py
├── version.json       # Canonical version number
└── CHANGELOG.md
```

## Common Commands

```bash
# Install dependencies (dev)
pip install -r requirements.txt

# Run locally
python Kuasarr.py

# Build Docker image
docker build -t kuasarr .

# Run via Docker
docker run -d \\
  --name kuasarr \\
  -p 8080:8080 \\
  -v /path/to/config:/config \\
  -e INTERNAL\_ADDRESS=http://localhost:8080 \\
  -e EXTERNAL\_ADDRESS=http://localhost:8080 \\
  -e TZ=Europe/Berlin \\
  ghcr.io/ritedt/kuasarr:latest
```

## Key Architecture Notes

### How Kuasarr Works (High Level)

1. **Indexer emulation**: Exposes a Newznab-compatible HTTP API. Radarr/Sonarr query it as if it were a usenet indexer.
2. **Scraper layer**: Searches configured DDL hostnames for matching releases. Hostnames are user-provided (not bundled).
3. **Link decryption**: Resolves CAPTCHA-protected containers (e.g. via FlareSolverr for Cloudflare-protected sites, or captcha-solving services for image CAPTCHAs).
4. **JDownloader dispatch**: Sends decrypted links to JDownloader via My-JDownloader API. JDownloader handles the actual downloading.
5. **Download client emulation**: Pretends to be SABnzbd so Radarr/Sonarr can track and import completed downloads.

### Configuration System

* Primary config: `/config/kuasarr.ini` — created on first run, managed via Web UI or manual edit
* Key sections: `\[Captcha]`, `\[WebUI]`, hostnames, FlareSolverr URL, JDownloader credentials
* ENV vars override INI for all sensitive values (preferred for Docker deployments)

### CAPTCHA Integration

* **DeathByCaptcha**: username+password or auth token (`DBC\_AUTHTOKEN`)
* **2Captcha**: API key (`TWOCAPTCHA\_API\_KEY`)
* Both use a shared retry/timeout config (`CAPTCHA\_TIMEOUT`, `CAPTCHA\_MAX\_RETRIES`, `CAPTCHA\_RETRY\_BACKOFF`)
* Service selection via `service = dbc` or `service = 2captcha` in `\[Captcha]`

### WebUI Auth

* Optional HTTP Basic Auth via `KUASARR\_WEBUI\_USER` + `KUASARR\_WEBUI\_PASS`
* API endpoints (`/api`, `/download/`, `/dbc/api/`) are **never** protected — Radarr/Sonarr use API key only
* Disabled by default (backwards compatible)

## Coding Standards & Agenten-Verwendung

* **Immer `/coding-standards` Skill nutzen** vor jeder Implementierung — Enforces PEP 8, Pythonic idioms, und Projekt-Konventionen
* **Immer Agenten nutzen** für Implementierungsaufgaben — Bevorzuge `Skill({skill: "..."})` oder `Agent({subagent_type: "..."})` gegenüber direkter Datei-Manipulation
* Nutze Sub-Agenten mit spezialisierten Rollen (z.B. `everything-claude-code:python-reviewer`, `everything-claude-code:planner`)
* Bevorzuge `/everything-claude-code:plan` für komplexe Features mit Multi-Model-Analyse

## Coding Conventions

* Follow existing Python style in `kuasarr/` — no enforced linter config found, keep consistent with surrounding code
* ENV vars: `SCREAMING\_SNAKE\_CASE`
* INI keys: `lowercase\_with\_underscores`
* Sensitive values (passwords, tokens, API keys) must **never** be hardcoded — always read from ENV or INI
* Version bumps: nur `Hier_Version_\u00c4ndern.txt` \u00e4ndern — CI propagiert an alle Stellen

## Important Constraints

* **This is NOT a torrent or usenet client.** Never implement NZB parsing, torrent handling, or magnet link support.
* **Never bundle hostnames.** Kuasarr intentionally ships without scrape targets — users provide these themselves.
* **Preserve SABnzbd + Newznab API contract.** Radarr/Sonarr integration depends on exact API shape — don't break existing endpoints.
* **Sonarr limitation**: All shows must use "Standard" series type. Anime/Absolute is not supported and never will be by design.
* **Multi-arch Docker**: Maintain compatibility with `linux/amd64`, `linux/arm64`, `linux/arm/v7` — don't introduce amd64-only dependencies.
* **Path mapping for JDownloader**: Download paths must be identical inside JDownloader and inside Radarr/Sonarr containers. Don't break this assumption.

## External Dependencies (Runtime)

These must be running and reachable by Kuasarr:

* **FlareSolverr** ≥ 3.4.4 — URL must include `/v1` path suffix
* **JDownloader 2** — connected to My-JDownloader cloud service
* **Radarr / Sonarr / LazyLibrarian** — configure Kuasarr as Newznab indexer + SABnzbd client

## Release Process

* Versioning in `version.json`
* Docker images published to GHCR: `ghcr.io/ritedt/kuasarr`
* Tags available on GitHub Container Registry
* CHANGELOG.md tracks changes per release

