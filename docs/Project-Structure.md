# Project Structure

## Repository Root

```
Kuasarr/
├── kuasarr/           # Main application package
├── docs/              # Developer documentation
├── scripts/           # Helper / release scripts
├── .github/           # GitHub Actions workflows
├── Kuasarr.py         # Application entrypoint
├── Dockerfile
├── requirements.txt
├── pyproject.toml
├── setup.py
├── version.json       # Canonical version (managed by CI)
├── Hier_Version_Ändern.txt  # Edit this for version bumps
├── CHANGELOG.md
├── AGENTS.md          # Guidelines for AI agents
└── CLAUDE.md          # Claude Code context
```

## `kuasarr/` Package Layout

| Directory | Responsibility |
|---|---|
| `kuasarr/api/` | HTTP endpoints for *arr clients and web UI |
| `kuasarr/downloads/` | Download submission, packaging, and mirror selection |
| `kuasarr/search/` | Search behavior and source integrations |
| `kuasarr/providers/` | Logging, notifications, sessions, metadata, web server |
| `kuasarr/storage/` | Config, setup flows, categories, SQLite state |
| `kuasarr/categories/` | Category mapping logic |
| `kuasarr/static/` | Web UI assets (logo, PWA manifest, etc.) |
| `kuasarr/webui/` | Web UI templates and frontend |

## Key Architecture Principle

Keep source-specific logic near the feature boundary that already exists. Source-specific scraping code belongs with existing source modules, not in shared layers.

The Newznab + SABnzbd API contract with Radarr/Sonarr/LazyLibrarian must not be broken. Do not change existing endpoint shapes without careful consideration.

## Entry Points

- `Kuasarr.py` — launches the application
- `version.json` — single source of truth for the version number (managed by CI from `Hier_Version_Ändern.txt`)
