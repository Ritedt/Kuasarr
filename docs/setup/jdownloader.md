# JDownloader 2 Setup

Kuasarr requires a **My-JDownloader** connected JDownloader 2.

## Installation

### Docker (recommended)

```bash
docker run -d \
  --name jdownloader \
  -p 5800:5800 \
  -v /path/to/downloads:/output \
  -v /path/to/jdownloader-config:/config \
  jlesage/jdownloader-2:latest
```

### Desktop

[Download JDownloader 2](https://jdownloader.org/download/index) and install it.

## Connect My-JDownloader

1. Open JDownloader 2
2. Go to **Settings** → **My.JDownloader.org**
3. Enable **My-JDownloader connection enabled**
4. Note your email and password

## Kuasarr Configuration

1. Open the Kuasarr WebUI
2. Go to **Settings** → **JDownloader**
3. Enter your My-JDownloader credentials:
   - **Email**: Your My-JDownloader email
   - **Password**: Your My-JDownloader password
   - **Device name**: Optional (e.g. `kuasarr`)

## Download Paths (important!)

Radarr/Sonarr must be able to access the same physical path as JDownloader.

### Example Setup

```yaml
# JDownloader
volumes:
  - /mnt/data/downloads:/output

# Radarr
volumes:
  - /mnt/data/downloads:/downloads

# Kuasarr (no download volume needed)
```

In Kuasarr: **Download Path** = `/output/Kuasarr/` (JDownloader perspective)
In Radarr: **Remote Path** = `/downloads/Kuasarr/` (Radarr perspective)

> **Tip**: Set up a separate download folder for Kuasarr in JDownloader to avoid conflicts with manual downloads.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Device not found" | Check My-JDownloader connection in JDownloader |
| "Download not found" | Paths must be identical for Radarr/Sonarr and JDownloader |
| Downloads stuck | Check JDownloader bandwidth limit and captcha settings |
