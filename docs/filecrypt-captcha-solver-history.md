# filecrypt Captcha-Solver — Versuchschronik

Diese Datei dokumentiert alle Versuche, die filecrypt-Container-Captchas in Kuasarr
automatisch zu lösen — mit Ergebnis und Erkenntnissen pro Versuch.

## Ausgangslage

filecrypt.cc ist einer der primären Container-Provider in Kuasarr. Die Captcha-Landschaft
auf filecrypt hat sich im Juni 2026 mehrfach geändert und besteht aus drei Varianten:

1. **CNL-only-Container**: kein Captcha nötig, AES-Payload direkt im Form.
2. **reCAPTCHA-v2**: `<div class='g-recaptcha' data-sitekey='6LcrmP8S…'>` + Token-Field.
3. **Circle-Captcha**: `<div class='circle_captcha'>` mit `<input type='image' src='/captcha/circle.php' name='button'>`.
4. **PoW-Captcha**: `<div class='pow-captcha' data-challenge data-difficulty>` mit versteckten
   `pow_id, pow_nonce, pow_elapsed, pow_pauses, pow_data, pow_x` Inputs.

Die ersten drei funktionieren automatisch. Nur PoW scheitert konsistent, weil
filecrypt serverseitig validiert, dass die `pow_data`/`pow_x`-Tokens aus einem Browser
stammen, dessen Fingerprint zum ausgestellten `cf_clearance`-Cookie passt.

---

## Versuch 1: Pure Python SHA-1 Solver (`ee6e942`)

**Ansatz**: SHA-1 brute-force in Python, Form-Felder `POW.data`/`POW.x` posten.

**Ergebnis**: ❌ filecrypt rejected (Token wird nicht akzeptiert).

**Fehler im ersten Entwurf**:

- Falsche Feldnamen (`POW.data` ≠ `pow_data` — filecrypt nutzt lowercase).
- Doppelpunkt fehlte: filecrypts JS-Worker hasht `challenge + ':' + nonce`, wir
  hashen `challenge + nonce` (kein Doppelpunkt).
- `clz32` vs. hex-Prefix: filecrypt zählt die Anzahl der **führenden Null-Bits** in
  der Binärdarstellung (`Math.clz32`); wir haben nur die ersten N Hex-Stellen
  geprüft — das ist eine schwächere Bedingung, die echte Lösungen verpasst.

---

## Versuch 2: SHA-1 + Form-Felder Fixes (`95140e1`, `b237447`)

- `POW.data` → `pow_data` (korrekte Kleinbuchstaben).
- Doppelpunkt in `SHA1(challenge + ':' + nonce)`.
- `clz32`-basierende Null-Bit-Zählung via `bin(digest_bytes).bit_length()`.
- 6 Form-Felder: `pow_id, pow_nonce, pow_elapsed, pow_pauses, pow_data, pow_x`.
- `Origin` + `Referer` Header auf SHA-1-POST.
- Node-Sidecar eingeführt, der `m.js.R()` und `s.js.S.collect()` in einer vm-Sandbox
  ausführt, um `pow_x` und `pow_data` zu generieren.

**Ergebnis**: ❌ filecrypt rejected weiterhin.

`pow_data` und `pow_x` werden serverseitig validiert. Die Sandbox-Fingerprint
(Chrome 126) matcht nicht den `cf_clearance`-Cookie (Chrome 149), den FlareSolverr
ausgestellt hat.

---

## Versuch 3: Cubic-Bézier Mouse Path (`85f83a3`)

**Ansatz**: Vor dem Captcha-Click eine animierte Bézier-Mausbewegung mit ~22
`mousemove`/`pointermove`-Events ausführen, um den motion-Fingerprint eines echten
Users zu imitieren. Danach der `mousedown`/`mouseup`/`click`.

**Ergebnis**: ❌ `executeJs` lief fehlerfrei, Bézier-Bewegung sichtbar, aber filecrypt
lehnte das Token weiter ab.

**Fazit**: Die Bézier-Kurve allein reicht nicht. filecrypt prüft entweder
`isTrusted` oder Properties, die unsere synthetischen Events nicht erfüllen
(z. B. echte Timing-Jitter, Touch-/Pointer-API-Konsistenz).

---

## Versuch 4: Node-Sidecar Setup (`e0132f5`, `5509015`)

- `nodejs npm` in Dockerfile ergänzt.
- `scripts/filecrypt_pow_sidecar.js` angelegt: `vm.createContext` + Fake-Browser-Env
  (navigator, screen, crypto.subtle, AudioContext, canvas, WebGL).
- Sidecar wird via `subprocess.run` aus dem Dispatcher aufgerufen.

**Ergebnis**: ❌ Tokens werden generiert (pow_x ≈ 92 chars, pow_data ≈ 1138 chars),
aber filecrypt lehnt sie ab.

Sandbox-Fingerprint ≠ echter Chrome-Fingerprint.

---

## Versuch 5: Sidecar-Reparaturen (mehrere Commits)

- `b16b191`: `tempfile`-Import fehlte → Sidecar fand sich selbst nicht.
- `b3107b4`: CF-Bypass für `/js/m.js` und `/js/s.js` (filecrypt challenged diese
  Pfade separat vom Container).
- `13cf0a3`: Striktere Circle-Captcha-Detection (`.find('input', type='image')`
  statt nur Class-Match, weil `circle_captcha` als CSS-Klasse auch in PoW-Markup
  vorkommt).
- `39d6545`: Sidecar bekommt `SIDECAR_USER_AGENT` / `SIDECAR_PLATFORM` aus dem
  Python-Wrapper und emit'etert vor `S.collect()` eine Mouse-Sequenz für nicht-leeres
  `pow_data`.

**Ergebnis**: ❌ Sidecar liefert Tokens, aber das Browser-Mismatch-Problem bleibt.
filecrypt lehnt weiter ab.

---

## Versuch 6: FlareSolverr executeJs im echten Chrome (`ba36ad1`)

**Kernidee**: `pow_data`/`pow_x` werden **im selben Chrome** erzeugt, der den
`cf_clearance`-Cookie hält. Das eliminiert das Fingerprint-Mismatch.

**Setup**:

- Persistente FS-Session: `_create_or_get_pow_session()` (cached in
  `shared_state.values["filecrypt_pow_session"]`).
- `_FS_POW_EXECJS`: ein JavaScript-Snippet, das im FlareSolverr-Chrome via
  `executeJs` läuft:
  1. Liest `challenge`, `difficulty`, `pow_id` aus dem gerenderten DOM.
  2. `fetch('/js/m.js?v=0f174e67')` + `fetch('/js/s.js?v=82c3f32b')` mit
     `credentials: 'same-origin'`.
  3. Strippt `export const` → `globalThis.`, eval'd via dynamic-Function-eval.
  4. Wartet bis `globalThis.R` und `globalThis.S` verfügbar sind.
  5. `S.start()`, `S.recordClick()` auf das `pow-captcha__box`-Element.
  6. Wartet 250 ms (entspricht dem realen Worker-Flow).
  7. Ruft `await globalThis.R()` und `await globalThis.S.collect()`.
  8. Liefert `pow_x` und `pow_data` als JSON-String.
- `_compute_pow_via_flaresolverr()` ruft das Snippet via
  `POST {cmd:"request.get", url, session, executeJs, maxTimeout:60000, waitInSeconds:20}` auf.
- Fallback: bei leerem `executeJsResult` greift der Node-Sidecar.

**Live-Test am 30.06.2026 13:30**:

```text
[13:30:16] Filecrypt PoW: flaresolverr returned empty executeJsResult
[13:30:16] Filecrypt PoW: flaresolverr tokens unavailable — falling back to Node sidecar
[13:30:17] Filecrypt PoW: final tokens pow_x=92 chars, pow_data=1138 chars
[13:30:17] Filecrypt still shows pow-captcha after SHA-1 POST
```

`executeJs` liefert einen leeren String. Vermutlich:

- Escape-Bug im Snippet (Python-`r"""` → JSON-Encoding → FS-interne Ent-escape-Pipeline),
- oder FS-Sandbox limitiert dynamische Function-Konstruktion / dynamische Imports.

Auf der FlareSolverr-Instanz erfolgreich manuell getestet (Session + executeJs +
gleiche Browser-Instanz lieferte `pow_x_len=19`, `pow_data_len=1195`). Im
Kuasarr-Subprocess-Aufruf kommt aber nichts zurück.

**Status**: ⚠️ Pfad ist verdrahtet, Snippet-Bug noch offen.

---

## Versuch 7: Promise-Return-Bug + Maglev-Anforderung (2026-06-30)

**Kernidee**: Der "Snippet-Bug noch offen" aus Versuch 6 ist ein konkret
identifizierter Promise-Return-Fehler im executeJs-Snippet. Plus die fehlende
Berücksichtigung des Chromium-V8-Maglev-JIT, der in Chromium 138+ die
filecrypt-SHA-1-Worker ausbremst.

### Bug-Diagnose

Per Code-Review von `rix1337/flaresolverr-next/src/flaresolverr_service.py`
verifiziert: FlareSolverr-next wrappt eingehende Snippets als
`(() => { <script> })()` (Block-Body Arrow) und führt sie via CDP
`Runtime.evaluate` mit `awaitPromise: True` aus.

Der **bisherige Snippet-Builder** in Kuasarr schrieb das Script als
`(async function(){ ... })();` — das ist ein Statement-Call, dessen
Promise-Return-Wert vom outer Arrow **nicht** zurückgegeben wird. Der outer
Arrow returnt implizit `undefined`. `awaitPromise: True` awaitet dann
`undefined` → Resultat ist leerer String. Genau das Symptom, das in Versuch 6
dokumentiert ist.

### Fix

Snippet-Builder auf das Pattern umstellen, bei dem die letzte Expression des
outer Arrows ein Promise ist:

```javascript
async function __kuasarr_pow_solve() {
    // ... bisheriger Body unverändert ...
    return JSON.stringify(out);
}
return __kuasarr_pow_solve();   // outer IIFE returnt Promise
```

### Zweite Voraussetzung: Maglev deaktivieren

Ab Chromium 138 aktiviert V8 standardmäßig Maglev als Mid-Tier JIT. Für
integer-/typed-array-lastigen SHA-1-Code (filecrypts Web-Worker) ist Maglev
**deutlich** langsamer als TurboFan — von ~3.5 M auf ~70 k Hashes/Sekunde
(Commit `rix1337/flaresolverr-next#41691a4`). Der Worker schafft es nicht
mehr innerhalb des `maxTimeout` (60 s).

**Fix**: `--js-flags=--no-maglev` ist im `rix1337/flaresolverr-next`-Image
**fest im Source** (`src/utils.py` → `get_webdriver()`) eingebaut. Es ist
**kein** zusätzliches Docker-Argument oder ENV-Variable nötig. Voraussetzung
ist nur das richtige Image. Siehe [docs/flaresolverr-setup.md](flaresolverr-setup.md).

### Code-Änderungen

- `kuasarr/scripts/filecrypt_pow_probe.js` (Z. 8 + Z. 166) — Snippet-Wrapper
  auf `async function __kuasarr_pow_solve(){...}; return __kuasarr_pow_solve();`
  umgebaut.
- `kuasarr/providers/captcha/dbc_dispatcher.py`:
  - `_load_fs_execjs()` lädt das Probe-Script (zwischen Versuch 6 und 7
    aus dem Inline-Python-String ausgelagert, damit kein JSON-Escape-Pipeline-
    Bug die Skripte korrumpiert).
  - `_compute_pow_via_flaresolverr()` Logging erweitert: leerer
    `executeJsResult` triggert `awaitPromise`-Hinweis mit Troubleshooting-
    Checkliste; erfolgreiche Tokens werden mit `pow_x_head` und
    `pow_data_head` geloggt.

### Test-Plan

**Vorbereitung (einmalig):**

1. Sicherstellen, dass FlareSolverr-Container auf
   `ghcr.io/rix1337/flaresolverr-next:latest` läuft (nicht
   `flaresolverr/flaresolverr`).
2. Kuasarr-Container neu starten mit den geänderten Snippets.

**Minimaler FS-Smoke-Test (vor dem ersten filecrypt-Versuch):**

```bash
curl -s -X POST http://flaresolverr:8191/v1 \
  -H 'Content-Type: application/json' \
  -d '{"cmd":"request.get","url":"https://example.com","executeJs":"return \"hello\""}'
```

Antwort muss `"executeJsResult": "hello"` enthalten. Bestätigt, dass
FlareSolverr grundsätzlich Snippets ausführt und `awaitPromise` korrekt
konfiguriert ist.

**Manueller Live-Test gegen filecrypt-Container:**

1. Über die WebUI oder via API-Aufruf einen filecrypt-Container-Link mit
   PoW triggern (z. B. einen Test-Release in Radarr/Sonarr).
2. Kuasarr-Logs beobachten:
   - **Erwartet nach Fix:** `Filecrypt PoW: flaresolverr tokens pow_id='...'
     pow_x=N chars pow_data=M chars pow_x_head='...' pow_data_head='...'`
     mit `N, M > 0` (typisch: N ≈ 90, M ≈ 1100).
   - **Falls weiterhin leer:** Der neue Hinweis-Text in
     `_compute_pow_via_flaresolverr()` zeigt die Troubleshooting-Checkliste
     (Image-Version, Snippet-Cache).
3. **Akzeptanztest:** Wenn Tokens gefüllt sind UND filecrypt den SHA-1-POST
   akzeptiert (kein erneutes pow-captcha im Response-Body), ist das Problem
   gelöst.
4. **Falls filecrypt die Tokens ablehnt:** cf_clearance-Fingerprinting-
   Hypothese ist bestätigt → Playwright-Micro-Service (Plan B) als nächster
   Schritt.

**Probe-Script isoliert testen:** Den Inhalt von
`filecrypt_pow_probe.js` (nach dem Fix) als `executeJs` an FlareSolverr
schicken — Antwort zeigt `out.steps` mit `surface`, `pow-div`, `fetch-m`,
`fetch-s`, `load-m`, `load-s`, `wait-globals`, idealerweise alle
`ok: true`.

### Ergebnis

Wenn `executeJsResult` nicht mehr leer ist, ist das **strukturelle** Problem
behoben. Die verbleibende Variable ist, ob filecrypt die berechneten Tokens
serverseitig akzeptiert (cf_clearance-Fingerprinting). Das wissen wir erst
nach dem ersten Live-Test gegen einen echten filecrypt-Container.

---

## Versuch 8: Race-Condition auf R()/S.collect() (30.06.2026)

**Kernidee**: Versuch 7 hat das **strukturelle** Problem behoben (Probe läuft
komplett durch, alle 7 Steps `ok: True`), aber die Tokens kommen leer zurück.
Live-Test vom 30.06.2026 14:53 (Batman.v.Superman Container):

```text
[14:53:45] Filecrypt PoW probe: {'step': 'wait-globals', 'ok': True, 'tries': 0, ...}
[14:53:45] Filecrypt PoW probe: {'step': 'S-recordClick', 'ok': True}
[14:53:45] Filecrypt PoW: flaresolverr tokens pow_id='DBE42CB80C' pow_x=0 chars pow_data=0 chars
[14:53:45] Filecrypt PoW: flaresolverr tokens unavailable — falling back to Node sidecar
[14:53:47] Filecrypt PoW: final tokens pow_x=92 chars, pow_data=1138 chars
[14:53:47] Filecrypt still shows pow-captcha after SHA-1 POST
```

**Beobachtungen aus dem Live-Test:**

1. **`wait-globals` mit `tries: 0`** — `R()` und `S.collect()` waren beim
   ersten Polling-Tick verfügbar, aber **nicht zwingend initialisiert**.
   `m.js` startet einen Web Worker für die SHA-1-Berechnung; `R()` returnt
   ein Promise, das erst resolved wenn der Worker durch ist. Die 250 ms
   Sleep zwischen `recordClick` und `R()`-Aufruf reichen dafür nicht.

2. **Der Node-Sidecar liefert im selben Lauf `pow_x=92 chars, pow_data=1138
   chars`** — filecrypts JS produziert also die Tokens, wenn man ihm genug
   Zeit lässt. Wir wissen also: das strukturelle Snippet ist OK, das
   **Timing** ist falsch.

3. **Selbst der Node-Sidecar wird vom filecrypt-Server abgelehnt**
   ("Filecrypt still shows pow-captcha after SHA-1 POST"). Das ist die
   cf_clearance-Fingerprinting-Hypothese aus Versuch 7 — kommt erst zum
   Tragen, NACHDEM wir konsistente Tokens haben.

### Versuch-8-Fix

**Zwei** Änderungen am Probe-Snippet:

1. **`S.recordPointer`-Sequenz vor `recordClick`** (6 Pointer-Events mit
   progressiver Koordinatenbewegung, wie im Node-Sidecar). Dadurch hat
   `S.collect()` einen nicht-leeren Maus-/Timing-Vektor, den s.js aggregieren
   kann. Ohne diese Sequenz wird `pow_data` per Default leer.

2. **`Promise.race` mit Timeout** um `R()` und `S.collect()` gewrappt:
   - `R()`: 30s Timeout — sicher unter `EXECUTE_JS_TIMEOUT` (60s) und
     großzügig für die SHA-1-Bruteforce.
   - `S.collect()`: 5s — s.js ist ein synchroner Aggregator.
   - Bei Timeout wird `null` returnt; das macht `pow_x` leer und der
     Probe-Step wird mit `r_timeout: true, r_call_ms: 30000` geloggt.
     Damit wissen wir **klar**, ob `R()` gegen den Timeout gerannt ist
     (Worker-Hänger) oder nur einen leeren String resolved hat.

3. **Timing-Logs** für beide Calls (`r_call_ms`, `s_collect_ms`), damit
   der nächste Versuch bei Bedarf die Timeouts gezielt anpassen kann.

### Versuch-8-Code-Änderungen

- `kuasarr/scripts/filecrypt_pow_probe.js` (Z. 134-180) — `S.recordPointer`-
  Sequenz, `withTimeout`-Helper, Timing-Logs.
- `kuasarr/providers/captcha/dbc_dispatcher.py` (`_compute_pow_via_flaresolverr`)
  — expliziter Warn-Log wenn `r_call_ms >= 29000` (Worker-Hänger erkannt).

### Test-Plan (ausstehend)

1. Kuasarr-Container neu starten.
2. filecrypt-Container triggern.
3. Logs prüfen:
   - **Erfolg:** Probe-Log `S-pointerSeq ok: true count: 6`, `R-call ok: true
     r_call_ms: 8000-25000 len: 90`, `S-collect ok: true s_collect_ms: 50
     len: 1100`. Dispatcher: `flaresolverr tokens pow_x=92 chars pow_data=1138
     chars`.
   - **Worker-Timeout:** `R-call timeout: true r_call_ms: 30000` →
     `EXECUTE_JS_TIMEOUT` auf 90s hochsetzen ODER `waitInSeconds` auf 30s.
   - **Akzeptanz:** filecrypt zeigt nach SHA-1-POST keinen `pow-captcha`
     mehr im Response-Body.
4. **Falls filecrypt die Tokens ablehnt** (cf_clearance-Hypothese):
   Übergang zu Plan B aus Versuch 7 (Playwright-Micro-Service, mit
   arm/v7-Einschränkung).

### Versuch-8-Ergebnis

Live-Test 01.07.2026 16:47 (Batman IMAX Remux UHD) hat die Race-Condition-
Hypothese **widerlegt** — und stattdessen einen trivialeren Bug aufgedeckt:

```text
[16:47:21] Filecrypt PoW probe: {'step': 'R-call', 'ok': True, 'r_call_ms': 82, 'len': 19}
[16:47:21] Filecrypt PoW probe: {'step': 'S-collect', 'ok': True, 's_collect_ms': 21, 'len': 1365}
[16:47:21] Filecrypt PoW: flaresolverr tokens pow_id='6EF561D888' pow_x=0 chars pow_data=0 chars
```

`R()` war in **82 ms** fertig (nicht gehängt!), lieferte ein 19-Zeichen-Token
(dasselbe `pow_x_len=19` aus dem manuellen FS-Test der Recherche).
`S.collect()` lieferte 1365 Zeichen. **Aber** der Dispatcher las
`pow_x=0 chars` — ein **Feldnamen-Bug**: die Probe speicherte nur
`out.pow_x_len`/`out.pow_x_head`, nie `out.pow_x`. Der Dispatcher sucht aber
nach `pow_x`/`pow_data`. Tokens wurden korrekt berechnet, aber nie ans
Dispatcher-JSON durchgereicht → leer → Node-Sidecar-Fallback.

Gefixt in Versuch 8c (Probe speichert jetzt die vollen Token-Strings).

---

## Versuch 8b: Circle-Captcha 2Captcha-Parsing-Bug (01.07.2026)

**Kernidee**: Der Circle-Captcha-Pfad (separat vom PoW-Pfad) scheiterte
konsistent mit "2Captcha task ready but no token". Die History hatte das
bislang als Worker-Problem (`ERROR_CAPTCHA_UNSOLVABLE`) eingestuft. Der
Live-Test 01.07.2026 10:56 (Batman.v.Superman UHD) zeigt aber ein anderes
Bild — und einen isolierten, leicht behebbaren Bug.

### Versuch-8b-Bug-Diagnose

Live-Log:

```text
[10:56:15] 2Captcha: Created task 83129573238
[10:56:30] 2Captcha task 83129573238 ready but no token
[10:56:30] DBC returned no coordinates for Circle-Captcha
[10:56:30] Token rejected by Filecrypt!
```

**Wichtig**: 2Captcha meldet die Aufgabe als **erfolgreich gelöst** (Status
`ready`), nicht als `unsolvable`. Der Worker hat also die korrekte Position
gefunden — nur Kuasarr extrahiert die Koordinaten nicht.

Root Cause: `_get_task_result` in
[`twocaptcha_client.py`](../kuasarr/providers/captcha/twocaptcha_client.py)
(Z. 185-208) kannte **nur token-basierte Solutions** und suchte nach
`token`/`text`/`gRecaptchaResponse`. Die 2Captcha-API liefert für
`CoordinatesTask` aber eine **andere Solution-Struktur**:

```json
{"solution": {"coordinates": [{"x": 358, "y": 268}]}}
```

Kein `token`, kein `text`. Die Solution fiel durch, `text` wurde `""`, und
`solve_coordinates_captcha` sprang sofort raus (`if not result.is_solved`).
DBC hat das Problem nicht, weil DBC Koordinaten als `"x,y"`-String liefert.

### Versuch-8b-Fix

`_get_task_result` so erweitern, dass eine nicht-leere `solution` ohne Token
als JSON-String zurückgegeben wird. Die bestehende Parsing-Logik in
`solve_coordinates_captcha` (Z. 415-423) decodiert das
`{"coordinates":[{"x":N,"y":N}]}` dann automatisch zu `(x, y)`.

```python
if status == "ready":
    solution = result.get("solution", {})
    token = (solution.get("token", "") or solution.get("text", "")
             or solution.get("gRecaptchaResponse", ""))
    if token:
        return CaptchaResult(text=token, ...)
    # Non-token solutions (e.g. CoordinatesTask) — hand back as JSON so the
    # caller's type-specific parser can decode it.
    if solution:
        return CaptchaResult(text=json.dumps(solution), ...)
```

### Versuch-8b-Ergebnis

Ausstehend — der nächste Circle-Captcha-Live-Test muss bestätigen, dass die
Koordinaten jetzt extrahiert werden und filecrypt den Klick akzeptiert.
Vorherige Fehldiagnose ("Worker-Problem") korrigiert: es war ein
Client-Parsing-Bug.

---

## Versuch 8c: PoW-Token-Feldname-Bug (01.07.2026)

**Kernidee**: Versuch 8s Race-Condition-Hypothese war falsch — `R()` ist in
82 ms fertig, nicht gehängt. Der echte Bug war trivial: die Probe berechnete
die Tokens korrekt, speicherte aber nur die Längen/Heads, nicht die
Vollstrings. Der Dispatcher las `pow_x`/`pow_data` → leer → Fallback.

### Versuch-8c-Bug-Diagnose

Live-Log (01.07.2026 16:47, Batman IMAX Remux):

```text
[16:47:21] Filecrypt PoW probe: {'step': 'R-call', 'ok': True, 'r_call_ms': 82, 'len': 19}
[16:47:21] Filecrypt PoW probe: {'step': 'S-collect', 'ok': True, 's_collect_ms': 21, 'len': 1365}
[16:47:21] Filecrypt PoW: flaresolverr tokens pow_id='6EF561D888' pow_x=0 chars pow_data=0 chars
```

`R()` lieferte 19 Zeichen (exakt das `pow_x_len=19` aus dem manuellen
FS-Test der Versuch-7-Recherche). `S.collect()` lieferte 1365 Zeichen.
Aber der Dispatcher las `pow_x=0 chars`.

Root Cause: `filecrypt_pow_probe.js` speicherte nur `out.pow_x_len`,
`out.pow_data_len`, `out.pow_x_head`, `out.pow_data_head` — aber **niemals**
`out.pow_x` / `out.pow_data`. Der Dispatcher in
`_compute_pow_via_flaresolverr` (Z. 324-326) sucht aber nach genau
`pow_id`/`pow_x`/`pow_data`. Feldnamen-Mismatch → leere Tokens →
Node-Sidecar-Fallback → filecrypt lehnt ab (cf_clearance-Mismatch des
Sidecars).

### Versuch-8c-Fix

Probe speichert jetzt die vollen Token-Strings:

```javascript
out.pow_x = pow_x;
out.pow_data = pow_data;
out.pow_x_len = pow_x.length;
out.pow_data_len = pow_data.length;
// heads bleiben für Diagnostik
```

Damit fließen die im echten Chrome erzeugten Tokens (mit zum cf_clearance
passendem Fingerprint) erstmals zum SHA-1-POST durch — statt die Node-Sidecar-
Tokens zu nehmen, deren Fingerprint nie passte.

### Versuch-8c-Ergebnis

**Bestätigt am 01.07.2026 16:57** (Batman EXTENDED BLURAY-GMB): Der
Feldname-Fix greift. Die im echten FlareSolverr-Chrome erzeugten Tokens
fließen erstmals zum SHA-1-POST durch — kein Node-Sidecar-Fallback mehr:

```text
[16:57:30] R-call ok: True r_call_ms: 85 len: 19
[16:57:30] S-collect ok: True s_collect_ms: 23 len: 1365
[16:57:30] Filecrypt PoW: flaresolverr tokens pow_id='F7D96ADED6'
           pow_x=19 chars pow_data=1365 chars
           pow_x_head='2.0.63.W1s2MDVdXQ==' pow_data_head='signal_Qfi4mI6IyboJCLi4mI6ICdw'
[16:57:30] Filecrypt still shows pow-captcha after SHA-1 POST
```

**Aber filecrypt lehnt weiterhin ab.** Damit ist die Pipeline-Seite
(Snippet, Token-Extraktion, Feldübergabe, POST) vollständig korrekt —
das verbleibende Problem ist **serverseitige Detection**, siehe Versuch 8d.

---

## Versuch 8d: Token-Decoding → Code 605 = headless-Chrome-Detection (01.07.2026)

**Kernidee**: Da die FS-Tokens jetzt sichtbar sind, können wir sie decodieren
und sehen **exakt**, warum filecrypt ablehnt. Die Tokens liefern einen
buchstäblichen Beweis statt einer Hypothese.

### pow_x-Decoding

`pow_x`-Format ist **keine Semver-Version**, sondern
`<const '2'>.<wJ>.<wx>.<base64(detectionCodes)>`:

- `wJ` = Success-Bitmask (Dezimal): Bit N gesetzt wenn Detection-Funktion #N
  Anomalien fand (sowhat=true).
- `wx` = Fail-Bitmask (Dezimal): Bit N gesetzt wenn Funktion #N keine
  Anomalie fand (sowhat=false) oder warf.
- 6 Detection-Funktionen (Bits 0-5): Window-Dims, screen-Mismatch,
  UA/WebGL-Konsistenz, Browser-Identität, languages, Bot/Headless.

Live-Token decodiert:

```text
pow_x = "2.0.63.W1s2MDVdXQ=="
  version-prefix = '2'   (konstant)
  wJ = 0                 → KEINE Funktion fand Anomalien
  wx = 63  (= 0b111111)  → ALLE 6 Funktionen "sauber"
  base64-payload = btoa("[[605]]")
```

Echter Desktop-Chrome (Referenz aus der Versuch-7-Recherche):

```text
pow_x = "2.8.55.<…>"
  wJ = 8   (0b001000) → Funktion #3 (Browser-Identität) fand Anomalien
  wx = 55  (0b110111)
  payload = [[402,"","chrome"],[403,""],[408,"chrome"],[604]]   (4 Codes)
```

### Code 605 entschlüsselt

`m.js` definiert 6 Detection-Funktionen mit Codes 100er–600er-Serie.
**Code 605** (0x25d, in der Bot/Headless-Funktion #5):

```javascript
if ("chrome" in window && !window.chrome.runtime && !window.chrome.webstore)
    wd.push([605]);   // HEADLESS CHROME DETECTED
```

Echter Chrome (mit GUI) hat `window.chrome.runtime` (mit `.connect()`,
`.sendMessage()` etc.) und `window.chrome.webstore`. **Headless Chrome /
FlareSolverr-Chrome** hat nur einen leeren `window.chrome`-Stub (damit die
grobe Prüfung `!!window.chrome` besteht) — die feingranulare Prüfung auf
`.runtime`/`.webstore` schlägt fehl → Code 605 feuert.

Das ist einer der bekanntesten Headless-Chrome-Indikatoren. Der Live-Test
bestätigt exakt: `window.chrome` existiert (sonst käme Code 408), aber
`.runtime` und `.webstore` fehlen.

### pow_data-Decoding (Teil)

`s.js.S.collect()` liefert `signal_` + custom-encoded base64 (reversed,
`a→@`, `e→.`, ohne Padding). Wire-Head decodiert zum JSON-**Tail**:

```text
pow_data_head = "signal_Qfi4mI6IyboJCLi4mI6ICdw"
  → tail: "t\":\"n\",\"ho\":\"n\"}"
  = …"pt":"n","ho":"n"}    (Feldanfang abgeschnitten)
```

`pt`/`ho` kommen aus `window.matchMedia`:

- `pt` = `matchMedia('(pointer)')` → Wert `"n"` (none). Echter Desktop-Chrome
  meldet `"fine"` → `"f"`.
- `ho` = `matchMedia('(hover)')` → Wert `"n"` (none). Echter Desktop-Chrome
  meldet `"hover"` → `"h"`.

Beide sind **weitere Automatisierungs-Signale**: Der FS-Chrome läuft in
einem Modus (headless / ohne interaktives Display), in dem `matchMedia` keine
Pointer-/Hover-Fähigkeit meldet. Die entscheidenden Cross-Check-Felder
(`workerData.webGLVendor`, `workerData.webdriver`, `workerData.cdpCheck1`,
`workerData.canvasFp`, `audioFp`, `pframes`-Phantom-Detects) sitzen im
JSON-**Head** und benötigen `pow_data.slice(-60)`-Logging, um sichtbar zu
werden (siehe offene TODOs).

### Fazit Versuch 8d

**Die FlareSolverr-executeJs-Pipeline ist vollständig korrekt und
vollständig diagnostiziert.** Tokens werden im echten Chrome erzeugt und
korrekt zum POST durchgereicht. filecrypt lehnt ab, weil der FS-Chrome
**mehrere Headless-/Automatisierungs-Signale** sendet:

1. **Code 605** (headless, primär): `window.chrome.runtime`/`.webstore` fehlen.
2. **`pt/ho = none/none`** (sekundär): `matchMedia` ohne Pointer/Hover.
3. Vermutlich weitere Felder im un-decodeten JSON-Head (`webGLVendor="NA"`,
   `webdriver`, `cdpCheck1`, `pframes`).

Das ist **kein Kuasarr-Bug mehr** — es ist die inhärente Grenze des
headless-Browser-Ansatzes. filecrypt hat bewusst mehrere Schichten
Bot-Detection eingebaut, und der FS-executeJs-Chrome durchschlägt keine davon
zuverlässig.

### Offene TODOs (nicht blockierend)

- `pow_data.slice(-60)`-Logging in der Probe ergänzen, um `workerData.*` und
  die weiteren Cross-Check-Felder sichtbar zu machen (vollständiges Bild,
  falls der Pfad jemals wieder aktiv verfolgt wird).
- Detection-Code-Vollständigkeit in m.js dokumentieren (402/403/408/604/605
  sind entschlüsselt; die 100er/200er/300er/500er-Serien sind in der
  Recherche erfasst, aber nicht alle im Live-Test aufgetaucht).

### Status

PoW-Auto-Solve ist mit der aktuellen Architektur (FlareSolverr-next headless)
**nicht zuverlässig erreichbar**, weil die Headless-Detection von filecrypt
das konzeptionelle Limit dieses Pfades ist. Der PoW-Pfad bleibt auf dem
**manuellen Handoff** (`/captcha`-Route) stehen, bis entweder:

1. FlareSolverr in einem **headed**-Modus (Xvfb/Virtual-Display) läuft, der
   `window.chrome.runtime`/`matchMedia` korrekt meldet — oder
2. Ein **echter** Browser (Playwright mit `Input.dispatchMouseEvent` +
   Anti-Detection-Hardening, oder headed Camoufox) den PoW löst.

Beide sind erhebliche Architektur-Änderungen und stehen unter dem
Kuasarr-Constraint `linux/arm/v7` (Playwright/Camoufox unterstützen kein
arm/v7 nativ).

---

## Aktueller Stand (30.06.2026)

| Captcha-Typ | Pfad | Status |
| --- | --- | --- |
| hide.cx API | `dbc_dispatcher._solve_hide_cx` | ✅ läuft (Post #67) |
| filecrypt CNL | `dbc_dispatcher._extract_filecrypt_links` | ✅ läuft |
| filecrypt reCAPTCHA-v2 | `dbc_dispatcher._solve_filecrypt_with_dbc` mit `g-recaptcha-response`-Field (`c2f31be`) | ✅ läuft |
| filecrypt Circle-Captcha | `dbc_dispatcher._solve_filecrypt_with_dbc` mit DBC/2Captcha-`CoordinatesTask` (`a73be2b`, `71191f5`) | ✅ läuft nach Parsing-Fix (Versuch 8b: `_get_task_result` extrahiert jetzt `coordinates`-Solution) |
| filecrypt PoW | `dbc_dispatcher._solve_filecrypt_pow_if_present` | ⚠️ Versuch 10 — Pipeline auf click-and-let-page-solve umgebaut (flaresolverr-next executeJs, Bézier-Klick → filecrypt-eigene JS rechnet + POST); erstes diagnose-fähiges Live-Test-Resultat ausstehend |
| filecrypt manueller Handoff | `kuasarr/api/captcha/provider_routes.py:serve_filecrypt_manual` | ✅ läuft (Browser-basierte Lösung durch User) |

---

## Empfohlene nächste Schritte

1. **FlareSolverr executeJs-Snippet debuggen** — das ist der einzige
   verbleibende Bug, der PoW blockiert. Erfolg würde PoW ohne neue Container
   lösen.
2. **Playwright-Micro-Service** als Plan B, wenn executeJs-Snippet nicht
   behebbar ist. Echter headless Chromium, der pro PoW eine Session öffnet.
3. **Circles-Clipboard-Solver fixen** — 2Captcha meldet UNSOLVABLE, was auf
   Worker-Schwierigkeiten (nicht Code) hindeutet. Eventuell auf
   `DBC` umstellen oder Bilder vorab manuell klassifizieren.
4. **CPU/RAM-Monitoring** der FS-Sessions: in Spitzenzeiten blockiert FS durch
   parallele `executeJs`-Aufrufe; Lastverteilung pro Container nötig.

---

## Bekannte Drittlösung: `rix1337/SponsorsHelper` (nicht integriert)

`rix1337` (Quasarr-Maintainer) bietet ein privates Docker-Image
`ghcr.io/rix1337/sponsors-helper:latest` an, das filecrypt-PoW in einer
**externen Helper-Container-Architektur** löst. Stand 30.06.2026 geprüft
und **bewusst nicht** in Kuasarr übernommen:

| Kriterium | SponsorsHelper | Kuasarr-Constraint |
| --- | --- | --- |
| Source / Lizenz | Closed-source | Open-source |
| Zugang | **Aktive GitHub-Spende an rix1337 erforderlich** (Sponsor-Gate im Container) | free, self-hosted, community-driven |
| Multi-Arch | `linux/amd64`, `linux/arm64` | **muss `linux/arm/v7`** ([CLAUDE.md](../../CLAUDE.md), [SPRINT_PLAN_V2.md](SPRINT_PLAN_V2.md)) |
| Captcha-Provider | **nur 2Captcha** | DBC + 2Captcha (User-Wahl) |
| Browser-Engine | delegiert an FlareSolverr (kein Chromium im Image) | bereits FlareSolverr im User-Setup |
| API-Protokoll | closed, kann jederzeit breaking ändern | muss API-Contract erhalten |

**Technisch redundanter Ansatz**: Quasarr's eigener `_solve_filecrypt_pow_if_present`
macht intern einen `MouseEvent('click')`-Dispatch via `flaresolverr-next`
`executeJs` — **identisch** mit Kuasarrs Commit `ba36ad1`. SponsorsHelper
orchestriert nur ein externer Wrapper mit dem gleichen FlareSolverr-Aufruf
und einem 5-Min-Refresh-Sponsor-Status. Kein technologischer Mehrwert
gegenüber dem aktuellen Kuasarr-Ansatz.

**Image-Aufbau** (verifiziert via GHCR-Manifest): `python:3.12.13-bookworm` + `uv`, 175 MB compressed, 11 Layer, **kein Browser im Image**. Port `9700/tcp` exposed, `/config`-Volume speichert GitHub-OAuth-Token (persistent!). ENV: `QUASARR_URL`, `QUASARR_API_KEY`, `FLARESOLVERR_URL`, `APIKEY_2CAPTCHA`, `TZ`.

**Architektur-Doku explizit ablehnend**:
[SPRINT_PLAN_V2.md](SPRINT_PLAN_V2.md) Z. 804 sagt:
*"SponsorsHelper nicht übernehmen — alle Quasarr-Referenzen auf
SponsorsHelper entfernen."* Diese Entscheidung wurde nach der Recherche
am 30.06.2026 **bestätigt** — die technischen Eigenschaften (closed-source,
Sponsor-Gate, kein arm/v7) sind nicht mit Kuasarrs Architekturprinzipien
vereinbar.

**Was Kuasarr aus dem SponsorsHelper-Pattern trotzdem nutzt**:

1. **API-Pattern für externe Helper**: Das `/sponsors_helper/api/*`-Schema
   (REST + `apikey`-Query + 300s-Refresh-Token) ist eine bewährte
   Vorlage, falls Kuasarr jemals einen eigenen optionalen Helper-Container
   anbieten will — dann aber mit offenem, dokumentiertem Protokoll.

2. **2Captcha-Integration ist einfach**: `APIKEY_2CAPTCHA` + HTTP-Calls.
   Kuasarr hat bereits einen 2Captcha-Client ([`a73be2b`][commit-a73be2b]).

3. **Für User, die SponsorsHelper trotzdem einsetzen wollen**: Den
   `/captcha`-Handoff-Pfad in [provider_routes.py][provider-routes]
   weiterpflegen — das ist die generische Schnittstelle für jeden externen
   Browser-basierten Solver (manuell oder automatisiert).

[commit-a73be2b]: https://github.com/Ritedt/Kuasarr/commit/a73be2b
[provider-routes]: ../kuasarr/api/captcha/provider_routes.py

---

## Geprüfte Alternative: Real-Debrid (löst PoW nicht, aber Hoster-Paywall)

Real-Debrid (`real-debrid.com`) wurde am 01.07.2026 als möglicher Weg
evaluiert, das filecrypt-PoW-Problem zu umgehen. **Ergebnis: RD löst das
PoW-Problem nicht**, ist aber als separate Stufe für Hoster-Downloads
nutzbar.

### Warum RD filecrypt-PoW nicht löst

- RD entschlüsselt **keine** filecrypt.cc-Container (weder als URL noch als
  Format). filecrypt ist kein unterstützter Hoster und kein unterstütztes
  Container-Format.
- `PUT /unrestrict/containerFile` akzeptiert nur **RSDF, CCF, CCF3, DLC**
  als Datei-Upload — und der DLC-Download bei filecrypt hängt ebenfalls
  hinter dem PoW-Captcha.
- RD greift **zu spät**: Kuasarr scheitert bereits daran, die Container-Seite
  zu öffnen und die Hoster-Links zu extrahieren. Wenn das geschafft ist, ist
  das PoW-Hindernis bereits überwunden.

### Wo RD trotzdem nützlich wäre (separate Stufe, separater Feature-Wunsch)

- RD unterstützt **11 von 12 Kuasarr-Standardhostern** (rapidgator,
  ddownload, turbobit, katfile, 1fichier, filefactory, keep2share, filer,
  nitroflare, uptobox, mediafire, mega — nur `uploaded` nicht).
- Für **direkte** Hoster-Links (nicht über filecrypt) könnte RD die
  Hoster-Paywall eliminieren: `/unrestrict/link` → unrestricted
  Download-URL → an JDownloader. JD bräuchte keinen Hoster-Account und kein
  Warten mehr.
- API: `POST https://api.real-debrid.com/rest/1.0/unrestrict/link`,
  Header `Authorization: Bearer <TOKEN>`, Body `link=<url>`. Response-Feld
  `download` ist die unrestricted URL.
- Multi-Arch: kein Problem (nur HTTP-Calls), funktioniert auf amd64/arm64/arm/v7.

### Möglicher Einfügepunkt (falls je gewünscht)

[`shared_state.py:download_package()`](../kuasarr/providers/shared_state.py)
— nach `filter_blocked_hosters()`, vor `device.linkgrabber.add_links()`.
Pro URL prüfen: RD-supported Hoster? → `/unrestrict/link` → `download`-URL
statt Original an JD senden. Neue `kuasarr/providers/debrid.py`, Config-Section
`[RealDebrid]`, ENV `REAL_DEBRID_API_TOKEN`.

**Status**: nicht integriert. RD-Abo nicht extra für filecrypt abschließen;
erst relevant, wenn das PoW-Problem anderweitig gelöst ist oder für direkte
Links als Download-Beschleuniger.

---

## Versuch 10: click-and-let-page-solve (01.07.2026)

**Kernidee**: Versuch 8d schloss, dass FlareSolverr-next `[[605]]` zeigte
und headless Chrome die Signale grundsätzlich nicht löst. Daraufhin FS-next
am Source gelesen (`utils.py`, `flaresolverr_service.py`) — **Korrektur**: auf
Linux/Docker läuft FS-next via `start_xvfb_display()` **headed** (echtes
`window.chrome.runtime`), nicht headless. Code 605 war deshalb ein **Artefakt
unseres Snippets**: das Probe-Skript injizierte `m.js`/`s.js` per
`<script textContent>` in die executeJs-isolierte Welt, wo der echte
Chromium-Fingerprint fehlte. Wir haben filecrypts main-world PoW-Logik
nie ausgeführt.

**Lösung** (reverse-engineered aus `rix1337/sponsors-helper`, dokumentiert in
`filecrypt-pow-reverse-engineering.md`): die executeJs-Snippet klickt
filecrypts PoW-Box (cubic-Bézier Pointer-Glide + Click) und überlässt filecrypts
eigener `m.js`/`s.js` das Rechnen + Submitten. filecrypt holt sich den Token
im echten headed-Chrome und POSTet ihn selbst — nichts wird extrahiert,
kein SHA-1-Bruteforce nötig.

```text
# Ablauf im Browser (gleicherheaded-Xvfb-Chromium wie CF-Bypass):

  1. wait-globals  (data-state="done" + pow_data Hidden-Input, max 6s)
  2. cubik-Bezier-Mauspfad zum .pow-captcha__box
  3. click-Sequenz: pointerover/enter, mouseover,
     pointerdown/mousedown, pointerup/mouseup, box.click()
  4. fetch(form.action, {credentials:'include', …}) — re-Submit im Browser
  5. Return {status, code, url, haspow, html}
```

### Code-Änderungen (jüngst, chronologisch)

- `kuasarr/scripts/filecrypt_pow_probe.js` — komplett neu: Bézier-Glide,
  Form-Submit-Intercept und `fetch`-POST im Browser, plus
  Fingerprint-Diagnostik (`hasChromeRuntime`, `pointer`, `hover`).
- `kuasarr/providers/captcha/dbc_dispatcher.py`:
  - `_compute_pow_via_flaresolverr` — neuer Returntyp:
    `_PowSolvedResponse | None` (statt `(pow_id, pow_x, pow_data)`).
    Parst die `executeJsResult`-JSON und surfaced die Diagnostik.
  - `_solve_filecrypt_pow_if_present` — Retry-Loop (3 Versuche) auf
    `haspow`/`status`, kein SHA-1-Bruteforce mehr.
  - **Gelöscht**: `_sha1_hex`, `_sha1_leading_zero_bits`,
    `_leading_zero_bits_of_bytes`, `_bruteforce_pow_sha1`,
    `_find_pow_sidecar`, `_compute_pow_sidecars` (Node-Fallback tot).
- `kuasarr/scripts/filecrypt_pow_sidecar.js` — gelöscht (Node-Sidecar tot).
- `scripts/poc_camoufox_filecrypt.py` — gelöscht (Camoufox-Pfad
  verworfen, da FS-next mit korrektem Snippet reicht).
- `pyproject.toml` — `kuasarr.scripts` listet jetzt nur noch den
  Probe-Snippet.

### Versuch-10-Ergebnis

**Erstes Live-Test-Resultat ausstehend.** Beim nächsten filecrypt-PoW-Live-Test
sollte der Dispatcher-Log einen `probe diag`-Eintrag zeigen, der die
605-Frage ein für alle Mal beantwortet:

- `hasChromeRuntime=True` + `pointer='fine'` + `hover='hover'`
  → Code 605 war tatsächlich nur unser Re-Injection-Artefakt →
  click-and-let-page-solve löst filecrypts PoW im headed-Xvfb-Chrome.

- `hasChromeRuntime=False` + `pointer='none'` + `hover='none'`
  → FS-next läuft NICHT headed oder Headless-Container bleibt
  Headless-Modus → der gepatchte Bin-Patch reicht nicht → Playwright o.Ä.
  nötig, manueller Handoff.

- `haspow=True` oder `status≠'ok'` nach Retry-Loop →
  filecrypt-Re-Submit-Regeln (wahrscheinlich isTrusted oder zusätzliche
  Signale, die wir noch nicht erkennen) → weitere Diagnostik nötig.

---

## Wichtige Commits (chronologisch)

| Hash | Inhalt |
| --- | --- |
| `ee6e942` | feat(filecrypt): Python SHA-1 PoW solver (no flaresolverr, no browser) |
| `85f83a3` | feat(filecrypt): cubic-Béziers mouse path for PoW (replace synthetic click) |
| `98a6b49` | feat(filecrypt): manual captcha handoff for PoW (no SponsorsHelper) |
| `4a95cb7` | feat(filecrypt): solve PoW-captcha via flaresolverr-next executeJs |
| `95140e1` | fix(captcha): return redirect() in check_captcha routing branches |
| `4165cfc` | fix(filecrypt): stricter Circle-Captcha detection |
| `71191f5` | fix(filecrypt): send Circle-Captcha image to DBC for real coords |
| `a73be2b` | fix(twocaptcha): use CoordinatesTask (not ImageToCoordinatesTask) |
| `c2f31be` | fix(filecrypt): use g-recaptcha-response field name for reCAPTCHA |
| `b3107b4` | fix(filecrypt-pow): use CF-bypass when fetching m.js / s.js |
| `b16b191` | fix(filecrypt-pow): add missing 'tempfile' import |
| `39d6545` | feat(filecrypt-pow): sidecar gets parent UA + emits mouse sequence |
| `13cf0a3` | fix(filecrypt-pow): log CF-bypass status + tighten JS-detection |
| `ba36ad1` | feat(filecrypt-pow): compute tokens in flaresolverr-next executeJs |
| *(ausstehend)* | fix(filecrypt-pow): Promise-Return-Pattern im Probe-Snippet (Versuch 7) |
| *(ausstehend)* | fix(filecrypt-pow): race-condition on R()/S.collect() in probe (Versuch 8) |
| *(ausstehend)* | docs(filecrypt): note on SponsorsHelper as known third-party solver (not adopted) |
| *(ausstehend)* | fix(twocaptcha): parse CoordinatesTask solution (Circle-Captcha "ready but no token") (Versuch 8b) |
| *(ausstehend)* | fix(filecrypt-pow): probe stores full pow_x/pow_data token strings (Versuch 8c) |
| *(ausstehend)* | docs(filecrypt): Versuch 8d token-decoding (Code 605 = headless detection) + Real-Debrid note |
| *(ausstehend)* | refactor(filecrypt-pow): click-and-let-page-solve pipeline (Bézier + fetch-POST, retry-loop, dead-code removal) (Versuch 10) |

---

## Erkenntnisse für die Zukunft

- filecrypt.cc ändert seine Captcha-UI oft und ohne Vorwarnung. Die
  `detect_filecrypt_captcha_type()`-Funktion in `quasarr/downloads/linkcrypters/filecrypt.py`
  ist die zentrale Stelle, an der die Heuristik gepflegt werden muss.
- Node.js kann filecrypts PoW-Tokens grundsätzlich erzeugen, aber die
  Sandbox-Fingerprints reichen nicht — entweder der echte Chrome (FS
  executeJs) oder Playwright liefert die passenden Tokens.
- Der beste nachhaltige Ansatz ist Playwright mit `Input.dispatchMouseEvent`
  (echte `isTrusted=true`-Events), da es sowohl das Motion-Fingerprinting
  als auch die Browser-Konsistenz in einem Schritt löst.
