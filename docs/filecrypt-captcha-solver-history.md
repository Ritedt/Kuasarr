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

```
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

## Aktueller Stand (30.06.2026)

| Captcha-Typ | Pfad | Status |
| --- | --- | --- |
| hide.cx API | `dbc_dispatcher._solve_hide_cx` | ✅ läuft (Post #67) |
| filecrypt CNL | `dbc_dispatcher._extract_filecrypt_links` | ✅ läuft |
| filecrypt reCAPTCHA-v2 | `dbc_dispatcher._solve_filecrypt_with_dbc` mit `g-recaptcha-response`-Field (`c2f31be`) | ✅ läuft |
| filecrypt Circle-Captcha | `dbc_dispatcher._solve_filecrypt_with_dbc` mit DBC/2Captcha-`CoordinatesTask` (`a73be2b`, `71191f5`) | ⚠️ 2Captcha gibt `ERROR_CAPTCHA_UNSOLVABLE` zurück (Worker-Problem) |
| filecrypt PoW | `dbc_dispatcher._solve_filecrypt_pow_if_present` | ⚠️ Versuch 7 — Promise-Return-Fix + Maglev-Anforderung implementiert, Live-Test ausstehend |
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
| _(ausstehend)_ | fix(filecrypt-pow): Promise-Return-Pattern im Probe-Snippet (Versuch 7) |

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
