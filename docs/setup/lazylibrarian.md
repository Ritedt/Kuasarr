# LazyLibrarian Setup

> **Status**: Experimentelle Unterstützung. Metadata-Probleme oder fehlende Covers müssen in LazyLibrarian gelöst werden.

## Indexer (Newznab)

1. LazyLibrarian öffnen → **Config** → **Providers**
2. Scrolle zu **Newznab Providers**
3. Füge hinzu:

| Feld | Wert |
|------|------|
| **Provider Name** | Kuasarr |
| **Newznab URL** | `http://kuasarr:9999` |
| **Newznab API** | Siehe Kuasarr WebUI → Einstellungen → API |

4. Klicke **Test**, dann **Add**

## Download Client (SABnzbd+)

1. LazyLibrarian → **Config** → **Downloaders**
2. Scrolle zu **SABnzbd+**
3. Konfiguriere:

| Feld | Wert |
|------|------|
| **SABnzbd Host** | `kuasarr` |
| **SABnzbd Port** | `9999` |
| **SABnzbd API Key** | Siehe Kuasarr WebUI |
| **SABnzbd Category** | `docs` |

> **Wichtig**: Verwende `docs` als Kategorie, um Konflikte mit Radarr/Sonarr zu vermeiden.

## Import-Einstellungen

1. **Config** → **Processing**
2. Aktiviere **Enable OpenLibrary api for book/author information**
3. Setze **Primary Information Source** auf `OpenLibrary`
4. Unter **Import languages** füge hinzu:
   - `, Unknown` (immer)
   - `, de, ger, de-DE` (für deutsche Bücher)

## Processing-Einstellungen

1. **Config** → **Processing** → **Folders**
2. Füge den Kuasarr-Downloadpfad hinzu:
   - Typischerweise `/downloads/Kuasarr/` oder `/output/Kuasarr/`
3. Dies ist notwendig, damit LazyLibrarian fertige Downloads erkennt

## Einschränkungen

- **Keine Metadata-Unterstützung**: Fehlende Covers oder Autoren-Infos müssen manuell korrigiert werden
- **Bessere Alternative**: [Readarr](https://readarr.com) (wenn stabil) oder manuelles Downloaden

## Fehlersuche

| Problem | Lösung |
|---------|--------|
| "No results found" | Prüfe, ob die Hostnames Bücher/EBooks enthalten |
| Downloads nicht erkannt | Download-Pfad in Processing-Einstellungen prüfen |
| Import schlägt fehl | Sprache auf `Unknown` setzen |
