# LazyLibrarian Setup

> **Status**: Experimental support. Metadata issues or missing covers must be resolved in LazyLibrarian.

## Indexer (Newznab)

1. Open LazyLibrarian → **Config** → **Providers**
2. Scroll to **Newznab Providers**
3. Add:

| Field | Value |
|-------|-------|
| **Provider Name** | Kuasarr |
| **Newznab URL** | `http://kuasarr:9999` |
| **Newznab API** | See Kuasarr WebUI → Settings → API |

4. Click **Test**, then **Add**

## Download Client (SABnzbd+)

1. LazyLibrarian → **Config** → **Downloaders**
2. Scroll to **SABnzbd+**
3. Configure:

| Field | Value |
|-------|-------|
| **SABnzbd Host** | `kuasarr` |
| **SABnzbd Port** | `9999` |
| **SABnzbd API Key** | See Kuasarr WebUI |
| **SABnzbd Category** | `docs` |

> **Important**: Use `docs` as category to avoid conflicts with Radarr/Sonarr.

## Import Settings

1. **Config** → **Processing**
2. Enable **Enable OpenLibrary api for book/author information**
3. Set **Primary Information Source** to `OpenLibrary`
4. Under **Import languages** add:
   - `, Unknown` (always)
   - `, de, ger, de-DE` (for German books)

## Processing Settings

1. **Config** → **Processing** → **Folders**
2. Add the Kuasarr download path:
   - Typically `/downloads/Kuasarr/` or `/output/Kuasarr/`
3. This is required for LazyLibrarian to detect completed downloads

## Limitations

- **No metadata support**: Missing covers or author info must be corrected manually
- **Better alternative**: [Readarr](https://readarr.com) (when stable) or manual downloading

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No results found" | Check if hostnames contain books/EBooks |
| Downloads not recognized | Check download path in Processing settings |
| Import fails | Set language to `Unknown` |
