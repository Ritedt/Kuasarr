# xREL.to Integration

Kuasarr kann die öffentliche xREL.to API nutzen, um korrekte Release-Größen und weitere Metadaten von Scene- und P2P-Releases abzurufen.

**Warum?** Die von den DDL-Seiten gescrapten Paketgrößen stimmen häufig nicht mit der tatsächlichen Release-Größe überein. Radarr und Sonarr vergleichen die angegebene Größe mit ihren eigenen Erwartungen — weicht sie zu stark ab, wird das Release übersprungen. xREL kennt die genaue Größe und korrigiert diesen Wert vor der Rückgabe an die Arrs.

## Aktivierung

```ini
[XRel]
enabled = true         ; xREL Größenabgleich einschalten
filter_nuked = false   ; Nuked-Releases aus den Ergebnissen ausblenden
```

## Wie es funktioniert

1. Nach der parallelen Quellensuche wird `_enrich_with_xrel()` aufgerufen.
2. Für jeden gefundenen Release wird `GET https://api.xrel.to/v2/release/info.json?dirname=<titel>` abgefragt (Scene).
3. Wenn kein Scene-Treffer vorhanden ist, wird `GET https://api.xrel.to/v2/p2p/rls_info.json?dirname=<titel>` als Fallback genutzt (P2P).
4. Die zurückgegebene Größe überschreibt den gescrapten Wert im Newznab-XML, das an Radarr/Sonarr gesendet wird.
5. Ergebnisse werden **24 Stunden** im In-Memory-Cache gehalten, um die xREL API zu schonen.

---

## Aktuell verwendete Felder

| Feld         | Quelle     | Verwendung                              |
|--------------|------------|-----------------------------------------|
| `size_bytes` | Scene+P2P  | Korrigiert Paketgröße in den Arrs       |
| `nuked`      | Scene      | Optionales Herausfiltern kaputter Releases |

---

## Verfügbare Felder für künftige Integration

### `group_name` (Scene + P2P)
Releasegruppe, z. B. `FLUX`, `YIFY`, `NOGRP`.

**Ideen:**
- Allow/Block-Liste: `[XRel] allowed_groups = FLUX,UTR` oder `blocked_groups = YIFY`
- Anzeige im WebUI-Ergebnis als Badge

---

### `english` (Scene)
`true`, wenn eine englische Tonspur vorhanden ist.

**Ideen:**
- Filter-Option „Nur Releases mit Englisch" für internationale Nutzer
- Kombinierbar mit dem bestehenden DL/ML-Sprachfilter der Quellen

---

### `video_type` (Scene)
Codec-String laut xREL, z. B. `x264`, `x265`, `HEVC`, `AVC`.

**Ideen:**
- `[XRel] require_video_codec = x265` — nur HEVC-Releases durchlassen
- Codec als Zusatzinfo im Titel anzeigen (z. B. `[DL] Film.2023.x265-GROUP`)

---

### `audio_type` (Scene)
Audio-Codec laut xREL, z. B. `DTS`, `AC3`, `AAC`, `TrueHD`.

**Ideen:**
- Gleiche Filterlogik wie `video_type`
- Kombination beider Felder für präzise Qualitätsprofile

---

### `ext_info_title` + `ext_info_type` (Scene + P2P)
Kanonischer Titel des Werks (`"Game of Thrones"`) und Medientyp (`"tv"`, `"movie"`, `"game"`, `"software"`, …).

**Ideen:**
- Titelabgleich: Warnung, wenn xREL-Titel stark vom Radarr/Sonarr-Titel abweicht
- Typabgleich: Verhindert Kategoriefehler (z. B. Movie-Release in Sonarr)

---

### `tv_season` + `tv_episode` (Scene)
Staffel- und Episodennummer laut xREL.

**Ideen:**
- Sanity-Check: Wenn xREL-Staffel ≠ gescrapte Staffel → Release markieren/überspringen
- Erkennt falsch getaggte Multi-Episode-Packs, die den Regex täuschen

---

### Nuke-Grund (Scene)
xREL liefert neben `nuke_rls = true` auch einen Nuke-Grund-String (z. B. `"INTERNAL"`, `"DUPE"`).

**Ideen:**
- Nuke-Grund als Tooltip/Badge im WebUI-Ergebnis anzeigen
- Nur bestimmte Nuke-Typen herausfiltern (z. B. `DUPE` ja, `INTERNAL` nein)

---

### Release-Zeitstempel (Scene + P2P)
xREL gibt den exakten Zeitpunkt der Veröffentlichung zurück.

**Ideen:**
- Feed-Ergebnisse nach xREL-Datum sortieren statt nach Scrape-Reihenfolge
- Sehr alte Releases (> N Tage) aus Feed-Ergebnissen ausblenden

---

### NFO-Inhalt (Scene, erfordert OAuth2)
xREL kann die Original-NFO-Datei einer Gruppe zurückgeben.

**Ideen:**
- NFO im WebUI-Detailbereich anzeigen
- Zusätzliche Metadaten aus dem NFO parsen (Codec, Sprache, Quelle)
- Erfordert OAuth2-Implementierung (`/nfo/release.json`)

---

## API-Referenz

| Endpoint                              | Beschreibung                     |
|---------------------------------------|----------------------------------|
| `GET /v2/release/info.json?dirname=`  | Scene-Release-Info               |
| `GET /v2/p2p/rls_info.json?dirname=` | P2P-Release-Info                 |
| `GET /v2/search/releases.json?q=`     | Suche (alternativ zu dirname)    |
| `GET /v2/nfo/release.json`            | NFO-Datei (OAuth2 erforderlich)  |

Basis-URL: `https://api.xrel.to/v2`
Authentifizierung: Keiner für öffentliche Endpunkte; OAuth2 für NFO und bewertete Endpunkte.
