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

## filecrypt.cc PoW-captcha: use the rix1337 fork, not upstream FlareSolverr

filecrypt's Proof-of-Work captcha (`<div class="pow-captcha">`) requires
FlareSolverr's `executeJs`-feature (added in `rix1337/flaresolverr-next` commit
`cb56470`). The standard `flaresolverr/flaresolverr` image does **not** ship
this feature, so the Kuasarr `_compute_pow_via_flaresolverr()` path would
always fall back to the Node.js sidecar (whose tokens are rejected because
the browser fingerprint doesn't match `cf_clearance`).

Additionally, the rix1337 fork ships `--js-flags=--no-maglev` baked into the
Chromium launch options (`src/utils.py` → `get_webdriver()`, see commit
`41691a4`). Without it, Chromium 138+ activates V8's Maglev mid-tier JIT,
which slows down filecrypt's integer-/typed-array-heavy SHA-1 web worker by
~40× (from ~3.5 M to ~70 k hashes/sec). The worker can no longer solve the
PoW within FlareSolverr's `maxTimeout` (60 s by default), and the
`executeJs` call terminates without a result.

**Both preconditions are met by simply using the rix1337 fork.** No extra
Docker argument, no environment variable, no custom entrypoint. Verify your
container:

```yaml
flaresolverr:
  image: ghcr.io/rix1337/flaresolverr:latest   # ← do not use ghcr.io/flaresolverr/flaresolverr
```

If filecrypt PoW still fails after switching images, see
[docs/filecrypt-captcha-solver-history.md](filecrypt-captcha-solver-history.md)
"Versuch 7" for the troubleshooting checklist.
