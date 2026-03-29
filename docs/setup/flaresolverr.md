# FlareSolverr Setup

[FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) bypasses Cloudflare protection for DDL sites.

## Installation

```bash
docker run -d \
  --name flaresolverr \
  -p 8191:8191 \
  -e TZ=Europe/Berlin \
  ghcr.io/flaresolverr/flaresolverr:latest
```

## Kuasarr Configuration

1. Open the Kuasarr WebUI
2. Go to **Settings** → **FlareSolverr**
3. Enter the URL: `http://your-server:8191/v1`

> **Important**: The URL must include the `/v1` path!

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

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "FlareSolverr not reachable" | Check if container is running: `docker ps` |
| Timeout | Increase timeout in Kuasarr settings |
| Cloudflare loop | Update FlareSolverr: `docker pull ghcr.io/flaresolverr/flaresolverr:latest` |
