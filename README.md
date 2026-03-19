![Kuasarr](kuasarr/static/logo-192.png)

# Kuasarr (Quasarr Fork)

[![GHCR Version](https://ghcr-badge.egpl.dev/ritedt/kuasarr/latest_tag?label=GHCR%20Version&logo=github)](https://github.com/Ritedt/Kuasarr/pkgs/container/kuasarr)
[![GitHub Release](https://img.shields.io/github/v/release/Ritedt/Kuasarr?label=Latest%20Release&logo=github)](https://github.com/Ritedt/Kuasarr/releases/latest)
[![Matrix Chat](https://img.shields.io/badge/Matrix-Join%20Chat-black?logo=matrix)](https://matrix.to/#/@kuasarr-support:envs.net)

Kuasarr connects JDownloader with Radarr, Sonarr and LazyLibrarian. It also decrypts links protected by CAPTCHAs.

Kuasarr pretends to be both `Newznab Indexer` and `SABnzbd client`. Therefore, do not try to use it with real usenet
indexers or download clients. It simply does not know what NZB or torrent files are.

## Table of Contents
- [Quick Start](#quick-start)
- [Improvements](#improvements)
- [Instructions](#instructions)
- [Kuasarr Docs](#kuasarr-docs)
- [License](#license)

## Quick Start

GHCR: [ghcr.io/ritedt/kuasarr](https://github.com/Ritedt/Kuasarr/pkgs/container/kuasarr)

```bash
docker run -d \
  --name kuasarr \
  -p 8080:8080 \
  -v /path/to/config/:/config \
  -e INTERNAL_ADDRESS=http://192.168.0.1:8080 \
  -e EXTERNAL_ADDRESS=http://192.168.0.1:8080 \
  -e TZ=Europe/Amsterdam \
  ghcr.io/ritedt/kuasarr:latest
```

All configuration, Hostnames, Flaresolverr, etc. lives inside `/config/kuasarr.ini`. Hostnames and FlareSolverr can also be managed via the Web UI. Available image tags are listed on [GitHub Container Registry](https://github.com/Ritedt/Kuasarr/pkgs/container/kuasarr).

## Improvements

- **Captcha Integration**: Automatic captcha solving via [DeathByCaptcha](https://deathbycaptcha.com?refid=1237432788a) or [2Captcha](https://2captcha.com/?from=26376359). 2Captcha is up to 50% cheaper for certain captcha types (e.g. CutCaptcha).
- **Hoster Filtering**: Exclude unwanted mirrors directly via the UI.
- **Multi-arch Docker images**: Official images now published for `linux/amd64`, `linux/arm64`, and `linux/arm/v7` (from v1.8.1).

# Instructions
1. Set up and run [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) 3.4.4 or later.
2. Set up and run [JDownloader 2](https://jdownloader.org/download/index).
3. Follow the next steps.

---

## FlareSolverr
1. Ensure your running FlareSolverr is reachable by Kuasarr.
2. Provide your FlareSolverr URL to Kuasarr during the setup process.
3. The full URL must include the version path, e.g., `http://192.168.1.1:8191/v1`.

---

## Kuasarr

Tell Kuasarr which sites to search for releases. It requires at least one valid source to start up.

> - By default, Kuasarr does **not** know which sites to scrape for download links.  
> - The setup will guide you through the process of providing valid hostnames for Kuasarr to scrape.  
> - If you need help, reach out on Matrix: [@kuasarr-support:envs.net](https://matrix.to/#/@kuasarr-support:envs.net).  
> - You may check sites like [Pastebin](https://pastebin.com/search?q=hostnames+Kuasarr) for user‑submitted suggestions.

---

## JDownloader

1. Ensure your running JDownloader is connected to the My JDownloader service.  
2. Provide your [My‑JDownloader‑Credentials](https://my.jdownloader.org) to Kuasarr during the setup process.

> - Consider setting up a fresh JDownloader before you begin.  
> - JDownloader must be running and available to Kuasarr.  
> - Kuasarr will modify JDownloader’s settings so downloads can be handled by Radarr/Sonarr/LazyLibrarian.  
> - If using Docker, ensure that JDownloader’s download path is available to Radarr/Sonarr/LazyLibrarian with **exactly the same** internal and external path mapping (matching only the external path is not enough).

---

## Radarr / Sonarr

Set up Kuasarr as a **Newznab Indexer** and **SABnzbd Download Client**:

1. **URL**: Use the `URL` from the **API Information** section of the console output (or copy it from the Kuasarr web UI).  
2. **API Key**: Use the `API Key` from the **API Information** section of the console output (or copy it from the Kuasarr web UI).  
3. Leave all other settings at their defaults.

> **Important notice for Sonarr**  
> - Ensure all shows (including anime) are set to the **Standard** series type.  
> - Kuasarr will never find releases for shows set to **Anime / Absolute**.

---

## LazyLibrarian

> **Important notice**
> - This feature is experimental and may not work as expected.
> - Kuasarr cannot help you with metadata issues, missing covers, or other LazyLibrarian problems.
> - Please report issues when one of your hostnames yields results through their website, but not in LazyLibrarian.

---

### Set up Kuasarr as a **SABnzbd+ Downloader**

1. **SABnzbd URL/Port**: Use port and host parts from `URL` found in the **API Information** section of the console output (or copy it from the Kuasarr web UI).  
2. **SABnzbd API Key**: Use the `API Key` from the **API Information** section of the console output (or copy it from the Kuasarr web UI).  
3. **SABnzbd Category**: Use `docs` to ensure LazyLibrarian does not interfere with Radarr/Sonarr.  
4. Press `Test SABnzbd` to verify the connection, then `Save changes`.

### Set up Kuasarr as a **Newznab Provider**:
1. **Newznab URL**: Use the `URL` from the **API Information** section of the console output (or copy it from the Kuasarr web UI).
2. **Newznab API** Use the `API Key` from the **API Information** section of the console output (or copy it from the Kuasarr web UI).
3. Press `Test` to verify the connection, then `Save changes`.

### Fix the `Importing` settings:
1. Check `Enable OpenLibrary api for book/author information`
2. Select `OpenLibrary` below `Primary Information Source`
2. Under `Import languages` add `, Unknown` (and for German users: `, de, ger, de-DE`).

### Fix the `Processing` settings:
1. Under `Folders` add the full Kuasarr download path, typically `/downloads/Kuasarr/`
2. If you do not do this,  processing after the download will fail.

## Captcha Configuration

Kuasarr supports multiple captcha solving services. Add your credentials to `kuasarr.ini`:

```ini
[Captcha]
# Choose your service: "dbc" or "2captcha"
service = dbc

# --- DeathByCaptcha settings ---
# Option 1: Username/Password
dbc_username = your_username
dbc_password = your_password

# Option 2: Auth Token (recommended)
dbc_authtoken = your_auth_token

# --- 2Captcha settings ---
twocaptcha_api_key = your_2captcha_api_key

# --- Advanced settings (optional) ---
timeout = 120
max_retries = 3
retry_backoff = 5
```

Or use environment variables:

```bash
docker run -d \
  --name kuasarr \
  -p 8080:8080 \
  -v /path/to/config/:/config \
  -e INTERNAL_ADDRESS=http://192.168.0.1:8080 \
  -e DBC_AUTHTOKEN=your_authtoken \
  -e TWOCAPTCHA_API_KEY=your_2captcha_key \
  -e TZ=Europe/Amsterdam \
  ghcr.io/ritedt/kuasarr:latest
```

Available environment variables:
- `DBC_USERNAME` - DeathByCaptcha username
- `DBC_PASSWORD` - DeathByCaptcha password
- `DBC_AUTHTOKEN` - DeathByCaptcha Auth token
- `TWOCAPTCHA_API_KEY` - 2Captcha API Key
- `CAPTCHA_TIMEOUT` - Timeout in seconds (default: 120)
- `CAPTCHA_MAX_RETRIES` - Max retries (default: 3)
- `CAPTCHA_RETRY_BACKOFF` - Seconds between retries (default: 5)

Links:
- [deathbycaptcha.com](https://deathbycaptcha.com?refid=1237432788a)
- [2captcha.com](https://2captcha.com?from=12345)

## WebUI Authentication (Optional)

Protect the Kuasarr WebUI with HTTP Basic Auth via **ENV** or **kuasarr.ini**.

**Option 1: Environment variables**
```bash
docker run -d \
  --name kuasarr \
  -p 8080:8080 \
  -v /path/to/config/:/config \
  -e INTERNAL_ADDRESS=http://192.168.0.1:8080 \
  -e KUASARR_WEBUI_USER=admin \
  -e KUASARR_WEBUI_PASS=your_secure_password \
  -e TZ=Europe/Amsterdam \
  ghcr.io/ritedt/kuasarr:latest
```

**Option 2: kuasarr.ini**
```ini
[WebUI]
user = admin
password = your_secure_password
```

**Important:**
- If **both** `KUASARR_WEBUI_USER` and `KUASARR_WEBUI_PASS` are set, the WebUI requires login.
- If either is missing or empty, authentication is **disabled** (backwards compatible).
- **API endpoints** (`/api`, `/download/`, `/dbc/api/`) are **never** protected by BasicAuth – Radarr/Sonarr continue to work with the API key only.
- For production use, always run behind HTTPS (reverse proxy recommended).

For systemd deployments, add to your unit file:
```ini
Environment=KUASARR_WEBUI_USER=admin
Environment=KUASARR_WEBUI_PASS=your_secure_password
```

## Install as PWA (Progressive Web App)

Kuasarr can be installed as a standalone app on your device:

1. **Desktop (Chrome/Edge)**: Click the install icon in the address bar or use the browser menu → "Install Kuasarr"
2. **Android**: Open Kuasarr in Chrome, tap the menu (⋮) → "Add to Home screen"
3. **iOS**: Open Kuasarr in Safari, tap Share → "Add to Home Screen"

> **Note**: PWA installation requires HTTPS. If running locally without TLS, use a reverse proxy (e.g., Nginx, Caddy) or access via `localhost`.

---

# Kuasarr Docs

- [Ultra.cc Installation](./ultracc_install.md)
- [Update Guide (systemd --user)](./update_guide.md)

---

## License

- MIT (see `LICENSE`)
- Fork of [`rix1337/quasarr`](https://github.com/rix1337/quasarr)
