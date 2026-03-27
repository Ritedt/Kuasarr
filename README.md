<div align="center">

![Kuasarr](kuasarr/static/logo-192.png)

# Kuasarr

**Bridge JDownloader with Radarr, Sonarr & LazyLibrarian**

[![GHCR](https://ghcr-badge.egpl.dev/ritedt/kuasarr/latest_tag?label=latest&color=blue)](https://github.com/Ritedt/Kuasarr/pkgs/container/kuasarr)
[![Release](https://img.shields.io/github/v/release/Ritedt/Kuasarr?logo=github&color=green)](https://github.com/Ritedt/Kuasarr/releases)
[![Matrix](https://img.shields.io/badge/Chat-Matrix-black?logo=matrix)](https://matrix.to/#/@kuasarr-support:envs.net)

</div>

Kuasarr emuliert einen **Newznab Indexer** und **SABnzbd Client**, um JDownloader in dein *arr-Setup zu integrieren. Keine NZBs, keine Torrents – reines Direct Download.

---

![Dashboard](docs/images/dashboard.png)

---

## Quick Start

```bash
docker run -d \
  --name kuasarr \
  -p 9999:9999 \
  -v /path/to/config:/config \
  ghcr.io/ritedt/kuasarr:latest
```

**Öffne `http://localhost:9999`** und folge dem Setup-Assistenten im WebUI. Keine Config-Dateien editieren nötig – alles geht über die Oberfläche.

### Optional: Umgebungsvariablen

| Variable | Beschreibung |
|----------|-------------|
| `TZ` | Zeitzone (z.B. `Europe/Berlin`) |
| `INTERNAL_ADDRESS` | Lokale URL (für interne API-Aufrufe) |
| `EXTERNAL_ADDRESS` | Externe URL (für Downloads) |

---

## Was macht Kuasarr?

| Feature | Beschreibung |
|---------|-------------|
| 🎨 **Modernes UI** | Intuitives Dark-Theme Webinterface – komplette Konfiguration ohne CLI |
| 🔍 **Indexer** | Durchsucht DDL-Seiten nach Releases |
| 🔓 **CAPTCHA** | Automatische Entschlüsselung via DeathByCaptcha oder 2Captcha |
| 📥 **Download** | Sendet Links direkt an JDownloader |
| 🎯 **Tracking** | Radarr/Sonarr erkennen fertige Downloads automatisch |

---

## Setup-Guides

Die Konfiguration der externen Tools ist ausgelagert:

| Tool | Guide |
|------|-------|
| [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) | [Setup →](docs/setup/flaresolverr.md) |
| [JDownloader 2](https://jdownloader.org) | [Setup →](docs/setup/jdownloader.md) |
| [Radarr](https://radarr.video) | [Setup →](docs/setup/radarr.md) |
| [Sonarr](https://sonarr.tv) | [Setup →](docs/setup/sonarr.md) |
| [LazyLibrarian](https://lazylibrarian.gitlab.io) | [Setup →](docs/setup/lazylibrarian.md) |

---

## Erweiterte Konfiguration

<details>
<summary>CAPTCHA-Services</summary>

Konfigurierbar über das WebUI oder Umgebungsvariablen:

| Variable | Service |
|----------|---------|
| `DBC_AUTHTOKEN` | [DeathByCaptcha](https://deathbycaptcha.com) |
| `TWOCAPTCHA_API_KEY` | [2Captcha](https://2captcha.com) |

</details>

<details>
<summary>WebUI-Authentifizierung (optional)</summary>

```bash
docker run -d \
  --name kuasarr \
  -p 9999:9999 \
  -v /path/to/config:/config \
  -e KUASARR_WEBUI_USER=admin \
  -e KUASARR_WEBUI_PASS=securepassword \
  ghcr.io/ritedt/kuasarr:latest
```

API-Endpunkte (`/api/*`, `/download/*`) bleiben ungeschützt für *arr-Integration.

</details>

<details>
<summary>PWA installieren</summary>

Kuasarr kann als Progressive Web App installiert werden:

- **Chrome/Edge**: Adressleiste → Install-Icon
- **Android**: Chrome-Menü → "Zum Startbildschirm hinzufügen"
- **iOS**: Safari → Teilen → "Zum Home-Bildschirm"

Erfordert HTTPS für volle Funktionalität.

</details>

---

## Unterstützte Quellen

- Nox.to (mit Login)
- Serienjunkies / Dokujunkies (mit Login)
- Filecrypt (mit Circle-Captcha Solver)
- Weitere über benutzerdefinierte Hostnames

---

## Architektur

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Radarr  │────→│         │────→│JDownloader
│ Sonarr  │     │ Kuasarr │     │   2     │
│ LazyLib │────→│  :9999  │────→└─────────┘
└─────────┘     └────┬────┘          │
                     │               ↓
                ┌────┴────┐     ┌─────────┐
                │Hostnames│     │  Downloads
                │FlareSolv│     └─────────┘
                └─────────┘
```

---

## Support

- **Matrix**: [@kuasarr-support:envs.net](https://matrix.to/#/@kuasarr-support:envs.net)
- **Issues**: [GitHub Issues](https://github.com/Ritedt/Kuasarr/issues)

---

## Lizenz

MIT License – Fork von [rix1337/quasarr](https://github.com/rix1337/quasarr)
