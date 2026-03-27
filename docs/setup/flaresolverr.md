# FlareSolverr Setup

[FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) umgeht Cloudflare-Schutz für DDL-Seiten.

## Installation

```bash
docker run -d \
  --name flaresolverr \
  -p 8191:8191 \
  -e TZ=Europe/Berlin \
  ghcr.io/flaresolverr/flaresolverr:latest
```

## Kuasarr-Konfiguration

1. Öffne das Kuasarr WebUI
2. Gehe zu **Einstellungen** → **FlareSolverr**
3. Trage die URL ein: `http://dein-server:8191/v1`

> **Wichtig**: Die URL muss den `/v1` Pfad enthalten!

## Docker Compose

```yaml
services:
  flaresolverr:
    image: ghcr.io/flaresolverr/flaresolverr:latest
    container_name: flaresolverr
    ports:
      - "8191:8191"
    environment:
      - TZ=Europe/Berlin
```

## Fehlersuche

| Problem | Lösung |
|---------|--------|
| "FlareSolverr not reachable" | Prüfe, ob der Container läuft: `docker ps` |
| Timeout | Erhöhe das Timeout in Kuasarr-Einstellungen |
| Cloudflare loop | FlareSolverr aktualisieren: `docker pull ghcr.io/flaresolverr/flaresolverr:latest` |
