# Radarr Setup

Richte Kuasarr als **Newznab Indexer** und **SABnzbd Download Client** ein.

## Indexer (Newznab)

1. Radarr öffnen → **Einstellungen** → **Indexer**
2. Klicke **+** → **Newznab**
3. Trage folgende Werte ein:

| Feld | Wert |
|------|------|
| **Name** | Kuasarr |
| **URL** | `http://kuasarr:9999` (oder deine Kuasarr-URL) |
| **API Key** | Siehe Kuasarr WebUI → Einstellungen → API |
| **Kategorien** | `2000,2010,2020,2030,2040,2045,2050,2060` |

4. Klicke **Test**, dann **Speichern**

## Download Client (SABnzbd)

1. Radarr öffnen → **Einstellungen** → **Download Client**
2. Klicke **+** → **SABnzbd**
3. Trage folgende Werte ein:

| Feld | Wert |
|------|------|
| **Name** | Kuasarr |
| **Host** | `kuasarr` (oder IP) |
| **Port** | `9999` |
| **API Key** | Siehe Kuasarr WebUI → Einstellungen → API |
| **Kategorie** | `movies` |

4. Klicke **Test**, dann **Speichern**

## Remote Path Mapping (falls nötig)

Falls Radarr und JDownloader unterschiedliche Pfade zum selben Verzeichnis haben:

1. **Einstellungen** → **Download Client** → **Remote Path Mappings**
2. Füge hinzu:
   - **Host** | `kuasarr`
   - **Remote-Pfad** | `/output/Kuasarr/` (JDownloader-Pfad)
   - **Lokaler Pfad** | `/downloads/Kuasarr/` (Radarr-Pfad)

## Quality Profiles

Kuasarr liefert meist 1080p-Releases. Empfohlenes Quality Profile:

1. **Einstellungen** → **Profile** → **Qualität**
2. Erstelle ein Profil mit bevorzugter Reihenfolge:
   - Bluray-1080p
   - WEBDL-1080p
   - HDTV-1080p

> **Hinweis**: 4K/Dolby Vision werden von den meisten DDL-Quellen nicht unterstützt.

## Indexer-Einschränkungen

In Radarr kannst du Releases nach Dateigröße filtern:

- **Minimale Größe**: 500 MB (verhindert Fake-Releases)
- **Maximale Größe**: 25 GB (optional, für langsame Verbindungen)
