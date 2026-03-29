# Security & Configuration

Treat configuration as sensitive.

## Secrets

- Do not commit real `kuasarr.ini` files, API keys, credentials, webhook URLs, or tokens.
- Sensitive values must always be provided via environment variables or the INI file at runtime — never hardcoded.
- Keep Docker config volumes persistent so generated state (config, database) is not lost between restarts.

## Hostnames

Do not commit real source hostnames or source lists to any tracked file. Hostnames must always be configured by the user at runtime via the Web UI or `kuasarr.ini`.

## Environment Variables

`INTERNAL_ADDRESS` must be valid for local development and Docker runs. `EXTERNAL_ADDRESS`, `KUASARR_WEBUI_USER`, and `KUASARR_WEBUI_PASS` should be set when exposing the UI beyond a trusted local network. Prefer authenticated access when using reverse proxies or public URLs.

## API Endpoints

The following endpoints are **never** protected by WebUI BasicAuth and rely solely on the API key:

- `/api`
- `/download/`
- `/dbc/api/`

This ensures Radarr, Sonarr, and LazyLibrarian continue to work regardless of WebUI auth settings.

## Reverse Proxy

For production use, always run Kuasarr behind HTTPS via a reverse proxy (e.g., Nginx, Caddy). Do not expose the application directly to the internet without TLS.
