# Radarr Setup

Configure Kuasarr as **Newznab Indexer** and **SABnzbd Download Client**.

## Indexer (Newznab)

1. Open Radarr → **Settings** → **Indexers**
2. Click **+** → **Newznab**
3. Enter the following values:

| Field | Value |
|-------|-------|
| **Name** | Kuasarr |
| **URL** | `http://kuasarr:9999` (or your Kuasarr URL) |
| **API Key** | See Kuasarr WebUI → Settings → API |
| **Categories** | `2000,2010,2020,2030,2040,2045,2050,2060` |

4. Click **Test**, then **Save**

## Download Client (SABnzbd)

1. Open Radarr → **Settings** → **Download Clients**
2. Click **+** → **SABnzbd**
3. Enter the following values:

| Field | Value |
|-------|-------|
| **Name** | Kuasarr |
| **Host** | `kuasarr` (or IP) |
| **Port** | `9999` |
| **API Key** | See Kuasarr WebUI → Settings → API |
| **Category** | `movies` |

4. Click **Test**, then **Save**

## Remote Path Mapping (if needed)

If Radarr and JDownloader have different paths to the same directory:

1. **Settings** → **Download Clients** → **Remote Path Mappings**
2. Add:
   - **Host** | `kuasarr`
   - **Remote Path** | `/output/Kuasarr/` (JDownloader path)
   - **Local Path** | `/downloads/Kuasarr/` (Radarr path)

## Quality Profiles

Kuasarr mostly delivers 1080p releases. Recommended quality profile:

1. **Settings** → **Profiles** → **Quality**
2. Create a profile with preferred order:
   - Bluray-1080p
   - WEBDL-1080p
   - HDTV-1080p

> **Note**: 4K/Dolby Vision are not supported by most DDL sources.

## Indexer Restrictions

In Radarr you can filter releases by file size:

- **Minimum size**: 500 MB (prevents fake releases)
- **Maximum size**: 25 GB (optional, for slow connections)
