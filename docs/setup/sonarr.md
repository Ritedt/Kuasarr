# Sonarr Setup

Richte Kuasarr als **Newznab Indexer** und **SABnzbd Download Client** ein.

> **Wichtig**: Kuasarr unterstützt nur **Standard**-Serientypen. Anime/Absolute Ordering wird nicht unterstützt.

## Indexer (Newznab)

1. Sonarr öffnen → **Einstellungen** → **Indexer**
2. Klicke **+** → **Newznab**
3. Trage folgende Werte ein:

| Feld | Wert |
|------|------|
| **Name** | Kuasarr |
| **URL** | `http://kuasarr:9999` (oder deine Kuasarr-URL) |
| **API Key** | Siehe Kuasarr WebUI → Einstellungen → API |
| **Kategorien** | `5000,5020,5030,5040,5050` |

4. Klicke **Test**, dann **Speichern**

## Download Client (SABnzbd)

1. Sonarr öffnen → **Einstellungen** → **Download Client**
2. Klicke **+** → **SABnzbd**
3. Trage folgende Werte ein:

| Feld | Wert |
|------|------|
| **Name** | Kuasarr |
| **Host** | `kuasarr` (oder IP) |
| **Port** | `9999` |
| **API Key** | Siehe Kuasarr WebUI → Einstellungen → API |
| **Kategorie** | `tv` |

4. Klicke **Test**, dann **Speichern**

## Serientyp ändern (wichtig!)

Für bestehende Serien:

1. Serie öffnen → **Bearbeiten**
2. Ändere **Serientyp** zu **Standard**
3. Speichern

Für neue Serien:

1. Serie hinzufügen → **Einstellungen** (Zahnrad)
2. Wähle **Serientyp: Standard**
3. Füge Serie hinzu

> **Warum?** Kuasarr findet keine Releases für Serien mit "Anime"-Typ, da diese absolute Episodennummern verwenden.

## Sprache & Qualität

### Sprache

1. **Einstellungen** → **Profile** → **Sprache**
2. Bevorzugte Sprache: `German` oder `English`

### Qualität

Empfohlenes Quality Profile für TV:

- HDTV-1080p (bevorzugt für schnelle Verfügbarkeit)
- WEBDL-1080p
- Bluray-1080p

## Release-Titel-Muster

DDL-Quellen verwenden oft deutsche Titel. Aktiviere in **Einstellungen** → **Indexer** → **Kuasarr**:

- **Übersetzte Titel verwenden**: Aktiviert

## Remote Path Mapping

Siehe [Radarr Setup](radarr.md) – gleiche Konfiguration, verwende `tv` als Kategorie.
