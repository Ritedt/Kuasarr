# FlareSolverr Setup

Kuasarr uses [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) to bypass
Cloudflare challenges on DDL sites. The original upstream is no longer actively
maintained; the Quasarr project (Kuasarr's upstream) has migrated to
**`ghcr.io/rix1337/flaresolverr-next`** (rix1337's fork), which is the actively
maintained, drop-in compatible target.

## Recommended image

```yaml
# docker-compose.yml
services:
  flaresolverr:
    image: ghcr.io/rix1337/flaresolverr-next:latest
    ports:
      - "8191:8191"
```

The protocol is standard FlareSolverr-compatible, so Kuasarr needs **no code
change** — just point the FlareSolverr URL at the new container (must include
the `/v1` suffix), e.g. `http://flaresolverr:8191/v1`. Configure it in the
WebUI (Settings → FlareSolverr) or `[FlareSolverr] url` in `kuasarr.ini`.

## Important limitation: AWS WAF is NOT solved by FlareSolverr

Neither the original FlareSolverr nor `-next` solves **AWS WAF** challenges
(e.g. the one protecting `imdb.com`, which returns HTTP 202). For IMDb title
resolution, Kuasarr therefore uses a JSON-API tier (see
`kuasarr/providers/imdb_metadata_api.py`): `api.imdbapi.dev` + the IMDb CDN
suggestion endpoint return structured JSON without touching the WAF-protected
HTML at all. FlareSolverr remains responsible for Cloudflare-protected DDL
sites, where it works reliably.
