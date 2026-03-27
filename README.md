<div align="center">

![Kuasarr](kuasarr/static/logo-192.png)

# Kuasarr

**Bridge JDownloader with Radarr, Sonarr & LazyLibrarian**

[![GHCR](https://ghcr-badge.egpl.dev/ritedt/kuasarr/latest_tag?label=latest&color=blue)](https://github.com/Ritedt/Kuasarr/pkgs/container/kuasarr)
[![Release](https://img.shields.io/github/v/release/Ritedt/Kuasarr?logo=github&color=green)](https://github.com/Ritedt/Kuasarr/releases)
[![Matrix](https://img.shields.io/badge/Chat-Matrix-black?logo=matrix)](https://matrix.to/#/@kuasarr-support:envs.net)

</div>

Kuasarr emulates a **Newznab Indexer** and **SABnzbd Client** to integrate JDownloader into your *arr stack. No NZBs, no torrents – pure direct download.

---

![Dashboard](docs/images/dashboard.jpeg)

---

## Quick Start

```bash
docker run -d \
  --name kuasarr \
  -p 9999:9999 \
  -v /path/to/config:/config \
  ghcr.io/ritedt/kuasarr:latest
```

**Open `http://localhost:9999`** and follow the setup wizard in the WebUI. No config file editing required – everything is done through the interface.

### Optional: Environment Variables

| Variable | Description |
|----------|-------------|
| `TZ` | Timezone (e.g. `Europe/Berlin`) |
| `INTERNAL_ADDRESS` | Local URL (for internal API calls) |
| `EXTERNAL_ADDRESS` | External URL (for downloads) |

---

## What is Kuasarr?

| Feature | Description |
|---------|-------------|
| 🎨 **Modern UI** | Intuitive dark-theme web interface – complete configuration without CLI |
| 🔍 **Indexer** | Searches DDL sites for releases |
| 🔓 **CAPTCHA** | Automatic decryption via DeathByCaptcha or 2Captcha |
| 📥 **Download** | Sends links directly to JDownloader |
| 🎯 **Tracking** | Radarr/Sonarr automatically detect completed downloads |

---

## Setup Guides

Configuration of external tools is outsourced to dedicated guides:

| Tool | Guide |
|------|-------|
| [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) | [Setup →](docs/setup/flaresolverr.md) |
| [JDownloader 2](https://jdownloader.org) | [Setup →](docs/setup/jdownloader.md) |
| [Radarr](https://radarr.video) | [Setup →](docs/setup/radarr.md) |
| [Sonarr](https://sonarr.tv) | [Setup →](docs/setup/sonarr.md) |
| [LazyLibrarian](https://lazylibrarian.gitlab.io) | [Setup →](docs/setup/lazylibrarian.md) |

---

## Advanced Configuration

<details>
<summary>CAPTCHA Services</summary>

Configurable via WebUI or environment variables:

| Variable | Service |
|----------|---------|
| `DBC_AUTHTOKEN` | [DeathByCaptcha](https://deathbycaptcha.com) |
| `TWOCAPTCHA_API_KEY` | [2Captcha](https://2captcha.com) |

</details>

<details>
<summary>WebUI Authentication (optional)</summary>

```bash
docker run -d \
  --name kuasarr \
  -p 9999:9999 \
  -v /path/to/config:/config \
  -e KUASARR_WEBUI_USER=admin \
  -e KUASARR_WEBUI_PASS=securepassword \
  ghcr.io/ritedt/kuasarr:latest
```

API endpoints (`/api/*`, `/download/*`) remain unprotected for *arr integration.

</details>

<details>
<summary>Install as PWA</summary>

Kuasarr can be installed as a Progressive Web App:

- **Chrome/Edge**: Address bar → Install icon
- **Android**: Chrome menu → "Add to Home screen"
- **iOS**: Safari → Share → "Add to Home Screen"

Requires HTTPS for full functionality.

</details>

---

## Supported Sources

- NX (with login)
- SJ / DJ (with login)
- Filecrypt (with Circle-Captcha solver)
- More via custom hostnames

---

## Architecture

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

## License

MIT License – Fork of [rix1337/quasarr](https://github.com/rix1337/quasarr)
