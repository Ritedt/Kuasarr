# JDownloader 2 Setup

Kuasarr benötigt einen mit **My-JDownloader** verbundenen JDownloader 2.

## Installation

### Docker (empfohlen)

```bash
docker run -d \
  --name jdownloader \
  -p 5800:5800 \
  -v /path/to/downloads:/output \
  -v /path/to/jdownloader-config:/config \
  jlesage/jdownloader-2:latest
```

### Desktop

[Lade JDownloader 2 herunter](https://jdownloader.org/download/index) und installiere es.

## My-JDownloader verbinden

1. Öffne JDownloader 2
2. Gehe zu **Einstellungen** → **My.JDownloader.org**
3. Aktiviere **My-JDownloader-Verbindung aktivieren**
4. Notiere dir E-Mail und Passwort

## Kuasarr-Konfiguration

1. Öffne das Kuasarr WebUI
2. Gehe zu **Einstellungen** → **JDownloader**
3. Trage deine My-JDownloader Credentials ein:
   - **E-Mail**: Deine My-JDownloader E-Mail
   - **Passwort**: Dein My-JDownloader Passwort
   - **Gerätename**: Optional (z.B. `kuasarr`)

## Download-Pfade (wichtig!)

Radarr/Sonarr müssen auf denselben physischen Pfad zugreifen können wie JDownloader.

### Beispiel-Setup

```yaml
# JDownloader
volumes:
  - /mnt/data/downloads:/output

# Radarr
volumes:
  - /mnt/data/downloads:/downloads

# Kuasarr (kein Download-Volume nötig)
```

In Kuasarr: **Download-Pfad** = `/output/Kuasarr/` (JDownloader-Perspektive)
In Radarr: **Remote-Pfad** = `/downloads/Kuasarr/` (Radarr-Perspektive)

> **Tipp**: Richte in JDownloader einen separaten Download-Ordner für Kuasarr ein, um Konflikte mit manuellen Downloads zu vermeiden.

## Fehlersuche

| Problem | Lösung |
|---------|--------|
| "Device not found" | Prüfe My-JDownloader Verbindung in JDownloader |
| "Download not found" | Pfade müssen für Radarr/Sonarr und JDownloader identisch sein |
| Downloads bleiben stehen | Prüfe JDownloader-Bandwidth-Limit und Captcha-Einstellungen |
