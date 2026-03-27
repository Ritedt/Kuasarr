# Development Guide

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

For an isolated environment (recommended):

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Kuasarr generates `kuasarr.ini` on first startup inside `/config/`. For local development, run it once to generate the config, then edit it directly.

Sensitive values can be provided via environment variables instead of the INI file — see `README.md` for the full list.

## Running Locally

```bash
python Kuasarr.py
```

The startup wizard guides you through hostname, JDownloader, and optional FlareSolverr configuration.

## Supporting Services

For local development you need:

- **FlareSolverr** ≥ 3.4.4 reachable by Kuasarr (URL must include `/v1` suffix)
- **JDownloader 2** connected to My-JDownloader cloud service

You can run supporting services via Docker:

```bash
docker run -d \
  --name flaresolverr \
  -p 8191:8191 \
  ghcr.io/flaresolverr/flaresolverr:latest
```

## Docker Build

```bash
docker build -t kuasarr .

docker run -d \
  --name kuasarr \
  -p 9999:9999 \
  -v /path/to/config:/config \
  -e INTERNAL_ADDRESS=http://localhost:9999 \
  -e EXTERNAL_ADDRESS=http://localhost:9999 \
  -e TZ=Europe/Berlin \
  kuasarr
```

## Quality Assurance

Run tests:

```bash
python -m pytest
```

Or with unittest directly:

```bash
python -X utf8 -m unittest discover -s tests
```

## Versioning

Only change `Hier_Version_Ändern.txt` for version bumps. CI propagates the value to `version.json` and all other locations automatically.
