# Sonarr Setup

Configure Kuasarr as **Newznab Indexer** and **SABnzbd Download Client**.

> **Important**: Kuasarr only supports **Standard** series types. Anime/Absolute ordering is not supported.

## Indexer (Newznab)

1. Open Sonarr → **Settings** → **Indexers**
2. Click **+** → **Newznab**
3. Enter the following values:

| Field | Value |
|-------|-------|
| **Name** | Kuasarr |
| **URL** | `http://kuasarr:9999` (or your Kuasarr URL) |
| **API Key** | See Kuasarr WebUI → Settings → API |
| **Categories** | `5000,5020,5030,5040,5050` |

4. Click **Test**, then **Save**

## Download Client (SABnzbd)

1. Open Sonarr → **Settings** → **Download Clients**
2. Click **+** → **SABnzbd**
3. Enter the following values:

| Field | Value |
|-------|-------|
| **Name** | Kuasarr |
| **Host** | `kuasarr` (or IP) |
| **Port** | `9999` |
| **API Key** | See Kuasarr WebUI → Settings → API |
| **Category** | `tv` |

4. Click **Test**, then **Save**

## Change Series Type (important!)

For existing series:

1. Open series → **Edit**
2. Change **Series Type** to **Standard**
3. Save

For new series:

1. Add series → **Settings** (gear icon)
2. Select **Series Type: Standard**
3. Add series

> **Why?** Kuasarr will not find releases for series with "Anime" type as they use absolute episode numbers.

## Language & Quality

### Language

1. **Settings** → **Profiles** → **Languages**
2. Preferred language: `German` or `English`

### Quality

Recommended quality profile for TV:

- HDTV-1080p (preferred for quick availability)
- WEBDL-1080p
- Bluray-1080p

## Release Title Patterns

DDL sources often use German titles. Enable in **Settings** → **Indexers** → **Kuasarr**:

- **Use translated titles**: Enabled

## Remote Path Mapping

See [Radarr Setup](radarr.md) – same configuration, use `tv` as category.
