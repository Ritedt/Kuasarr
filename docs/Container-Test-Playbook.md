# Container-Test-Playbook

Black-Box-Test eines laufenden Kuasarr-Containers über die Newznab-/SABnzbd-API.
Geht ohne Quellcode-Zugriff und ohne Test-Framework — gedacht für den Abgleich
nach einem Release oder nach einem Update auf einer echten Maschine (z. B. Unraid).

Der Unit-Test-Teil bleibt in [Testing.md](Testing.md).

---

## 0. Vorbereitung

| Variable | Wert |
|---|---|
| `URL` | `http://<host>:9999` |
| `KEY` | API-Key aus dem Start-Log |

```bash
URL=http://192.168.178.5:9999
KEY=<64 Hex-Zeichen>
```

> **Achtung `!` am Key.** Das Start-Log schreibt den Key als `"<hex>!"` aus, das
> gespeicherte `!` gehört aber **nicht** dazu. Bei `KEY` **ohne** `!` verwenden.
> Sonst antwortet `/api` mit `403 Invalid API Key`. Der korrekte Key steht
> weiter unten im Log unter „API Information“ bereits ohne `!`.

Der Key lässt sich alternativ aus dem Log ziehen:

```bash
docker logs kuasarr 2>&1 | grep -A2 'API Information' | grep -oE '[0-9a-f]{64}'
```

---

## 1. Erreichbarkeit

```bash
curl -s -o /dev/null -w '%{http_code}\n' "$URL/"
```

Erwartet: `200`, `Server: WSGIServer`. **Der Port ist 9999**, nicht 8080 — siehe
`EXPOSE` im Dockerfile. Der Server bindet auf `0.0.0.0`.

---

## 2. API-Key

```bash
curl -s -o /dev/null -w '%{http_code}\n' "$URL/api?t=caps&apikey=$KEY"
```

| Code | Bedeutung |
|---|---|
| `200` | Key gültig |
| `401` | `Missing API Key` — Parameter fehlt komplett |
| `403` | `Invalid API Key` — Key stimmt nicht (meist das `!`-Problem) |

**Kontrolle:** ein Key mit angehängtem `!` **muss** 403 liefern. Wenn er 200
liefert, wird intern ein anderer Key verglichen als der geloggte.

---

## 3. Newznab-Fähigkeiten

```bash
curl -s "$URL/api?t=caps&apikey=$KEY"
```

Prüfen: valides XML, `<title>kuasarr Indexer</title>`, eine `<search>`-Sektion.

> **Erwartungswecker:** `<search supportedParams="q">` wird angekündigt, aber
> `q` wird für `movie`/`tvsearch` **nicht ausgewertet** — siehe Schritt 6. Das
> ist kein Testfehler, aber eine irreführende Anzeige.

---

## 4. Feed (Textsuche / Discover)

Der Feed wird über `t=movie` **oder** `t=tvsearch` **ohne `imdbid`** ausgelöst —
dann ist `is_feed` wahr und Kuasarr liefert die neuesten Releases des Hosters.

```bash
curl -s "$URL/api?t=movie&limit=25&apikey=$KEY"   | grep -c '<item>'
curl -s "$URL/api?t=tvsearch&limit=25&apikey=$KEY" | grep -c '<item>'
```

Erwartet: `25` für beide. Feed-Suchen dauern 1–3 s, weil gescraped wird.

> **Ohne `t=` gibt es kein Ergebnis**, sondern `[ERROR] Unknown general request` —
> auch nicht mit `limit`. Das ist der häufigste Fehlalarm beim Smoke-Test: die
> Anfrage sieht plausibel aus und liefert trotzdem eine leere Antwort.

---

## 5. Serien- und Filmsuche über IMDB

Kuasarr mappt **ausschließlich über `imdbid`**. `q` wird ignoriert und liefert
stattdessen den generischen Feed.

```bash
# Serie, Staffel
curl -s "$URL/api?t=tvsearch&imdbid=tt0397306&season=19&apikey=$KEY" | grep -c '<item>'

# Film
curl -s "$URL/api?t=movie&imdbid=tt15239678&apikey=$KEY" | grep -c '<item>'
```

**`0` Treffer ist das übliche Ergebnis, wenn nichts konfiguriert ist.** Im Log
steht dann:

```
IMDb request blocked for tt0397306 (status 202), retrying via FlareSolverr
FlareSolverr fallback for IMDb tt0397306 failed: FlareSolverr URL not configured in shared_state.
dl: no title for IMDb tt0397306
```

IMDb antwortet auf direkte Anfragen mit `202` (Challenge). Kuasarr fällt dann auf
FlareSolverr zurück — und findet keine, wenn keine URL hinterlegt ist.

> **Ohne FlareSolverr ist die IMDB-Suche funktionsunfähig**, egal wie korrekt die
> Credentials sind. Das ist der häufigste Fehlalarm beim Testen.

### Kontrolltest, um „IMDB kaputt“ von „Inhalt fehlt“ zu unterscheiden

```bash
# irgendeine ID, die es auf dem Hoster sicher gibt
curl -s "$URL/api?t=movie&imdbid=tt0111161&apikey=$KEY" | grep -c '<item>'
```

Bleibt es bei `0`, ist die **Auflösung** kaputt (FlareSolverr/IMDb), nicht der
Katalog.

---

## 6. Was `q` wirklich tut

```bash
curl -s "$URL/api?t=movie&q=Dune&apikey=$KEY"              | md5sum
curl -s "$URL/api?t=movie&q=zzzzqmarkertest123&apikey=$KEY" | md5sum
```

**Erwartet: identische Hashes.** Das beweist, dass `q` durchgereicht, aber nicht
als Filter verwendet wird. Divergieren die Hashes, hat jemand `q`-Support
eingebaut — dann lohnt sich ein genauerer Test.

---

## 7. Download-Envelope (der Weg von Radarr/Sonarr)

Es gibt **keine** SABnzbd-Client-API (`?mode=version` / `?mode=history`) — solche
Pfade liefern 404. Stattdessen legt Kuasarr ein synthetisches NZB-Envelope an,
das auf den echten Link zeigt. Der `payload` ist urlsafe-Base64 von

```
title|url|mirror|size_mb|password|imdb_id
```

```bash
P=$(python3 -c "
import base64
print(base64.urlsafe_b64encode(
  'Test.Release.S01E01.1080p|https://example.invalid/file.bin|dl|500|geheim|tt0397306'
  .encode()).decode())")

# GET: gibt das NZB-Envelope zurück
curl -s "$URL/download/?payload=$P"
# -> <nzb><file title="..." url="..." mirror="dl" size_mb="500"
#          password="geheim" imdb_id="tt0397306"/></nzb>

# POST: meldet Erfolg an den Arr-Client
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"payload":"'"$P"'"}' "$URL/api?apikey=$KEY"
# -> {"status": true, "nzo_ids": []}
```

Erwartet: HTTP 200 in beiden Fällen, und im NZB exakt die sechs Felder in
Reihenfolge. Fehlt ein Feld oder ist die Reihenfolge vertauscht, ist die
Envelope-Erzeugung kaputt — daran hängt der Radarr/Sonarr-Import.

---

## 8. Logs auswerten

```bash
docker logs --tail 100 kuasarr 2>&1 | grep -viE '^\s*$'
```

| Meldung | Bedeutung |
|---|---|
| `Login verification failed for: "dl"` | data-load.me-Login falsch |
| `Session successfully created for: "dl"` | Hoster-Login ok |
| `Direct connection to JDownloader established` | My-JDownloader-Credentials ok |
| `Connection to JDownloader successful. Device name: ...` | JD verbunden |
| `Captcha: Not configured` | kein DBC/2Captcha-Token |
| `FlareSolverr URL not configured` | IMDB-Suche tot (Schritt 5) |
| `Ignoring search request ... only imdbid searches are supported` | `q` benutzt, erwartet |
| `Unknown general request: {...}` | `t=` fehlt oder Tippfehler |

**Reihenfolge beachten:** Kuasarr prüft erst den Hoster-Login, dann My-JDownloader,
dann Captcha. Ein Login-Fehler ganz oben im Log blockiert alles danach — er ist
nicht die *eigentliche* Ursache, wenn weiter unten noch „credentials required“
steht.

---

## 9. Pflichtprüfungen vor „läuft“

```bash
URL=...; KEY=...
P=$(python3 -c "
import base64
print(base64.urlsafe_b64encode(
  'T.S01E01|https://example.invalid/f.bin|dl|500|geheim|tt0397306'.encode()).decode())")

printf 'Erreichbar   : %s\n' "$(curl -s -o /dev/null -w '%{http_code}' $URL/)"
printf 'API-Key      : %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "$URL/api?t=caps&apikey=$KEY")"
printf 'Feed         : %s Items\n' "$(curl -s "$URL/api?t=movie&limit=25&apikey=$KEY" | grep -c '<item>')"
printf 'IMDB-Suche   : %s Items (0 = FlareSolverr fehlt)\n' \
  "$(curl -s "$URL/api?t=movie&imdbid=tt0111161&apikey=$KEY" | grep -c '<item>')"
printf 'NZB-Envelope : %s\n' \
  "$(curl -s "$URL/download/?payload=$P" | grep -oE 'imdb_id=\"[^\"]*\"')"
```

Ein Container gilt als funktionsfähig, wenn **Erreichbarkeit, API-Key und Feed**
grün sind. Die IMDB-Suche ist nur mit konfiguriertem FlareSolverr aussagekräftig.

---

## Bekannte Fallen

1. **Port 8080 in der Projektdoku.** `CLAUDE.md` zeigt `-p 8080:8080`; im
   Container lauscht ausschließlich 9999.
2. **`!` im geloggten API-Key** ist nicht Teil des Keys (Schritt 0).
3. **`q` wird nicht ausgewertet**, `supportedParams="q"` täuscht.
4. **FlareSolverr muss in Kuasarr eingetragen sein**, nur laufen zu lassen reicht
   nicht — sonst bleiben alle IMDB-Suchen leer.
5. **Ein früher Login-Fehler verdeckt die eigentliche Ursache** — immer bis zum
   Ende des Logs lesen.