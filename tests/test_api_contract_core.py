# -*- coding: utf-8 -*-
"""Der Vertrag zwischen der React-WebUI und der JSON-API.

Die WebUI liest ihre Antworten ueber einen einzigen Client, der zwei
Sachen voraussetzt: eine ``data``-Huelle bei Erfolg und eine
``{"error": {"message": ...}}``-Huelle bei Fehlern. Vorher galten drei
parallelen Schemata nebeneinander, und Bottle lieferte fuer jeden
``abort()`` eine HTML-Seite. ``response.json()`` scheiterte daran, der
``catch`` schluckte es, und der Nutzer sah immer ``Unknown error``.

Diese Tests fahren echte Bottle-Routen an - nur die Konfiguration ist
ersetzt, damit sie weder die ``kuasarr.ini`` des Entwicklers noch die
Zertifikate des Realsystems anfasst.
"""

import io
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import bottle


class _FakeConfig:
    """Minimaler Config-Ersatz: nur dict, nur die geteilten ``get``/``save``."""

    def __init__(self, section, values):
        self._values = values

    def get(self, key):
        return self._values.get(key)

    def save(self, key, value):
        self._values[key] = value


def _make_config(store):
    def factory(section):
        return _FakeConfig(section, store.setdefault(section, {}))
    return factory


class _FakeDatabase:
    """Nur die drei Zugriffe, die die Statistik-Provider beim Start tun.

    Der echte ``DataBase`` erwartet eine offene SQLite-Datei. Fuer den
    API-Vertrag reicht eine Attrappe: sie haelt keine Zeilen, liefert also
    auch keine, die einen Test in die Irre fuehren koennte.
    """

    def __init__(self, name):
        self.name = name
        self._conn = sqlite3.connect(":memory:")

    def retrieve(self, key):
        return None

    def store(self, key, value):
        pass

    def update_store(self, key, value):
        pass


class _FakeLock:
    """`get_api` verlangt den Shared-State-Lock; hier wird nichts geteilt."""

    def acquire(self, *args, **kwargs):
        return True

    def release(self):
        pass

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False


def _environ(path="/", method="GET", query="", body=b"", headers=None):
    env = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "SERVER_NAME": "kuasarr",
        "SERVER_PORT": "80",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(body),
        "wsgi.errors": io.StringIO(),
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }
    for name, value in (headers or {}).items():
        env["HTTP_" + name.upper().replace("-", "_")] = value
    return env


class _Response:
    """Das, was ein Bottle-``HTTPResponse`` dem Aufrufer liefert."""

    def __init__(self, status, headers, body):
        self.status_code = int(status.split(" ", 1)[0])
        self.headers = {k.lower(): v for k, v in headers}
        self.body = body

    @property
    def text(self):
        return self.body.decode("utf-8", "replace")

    @property
    def content_type(self):
        return self.headers.get("content-type", "")

    def json(self):
        return json.loads(self.text)


class _ApiCase(unittest.TestCase):
    """Baut die echte App und bindet pro Aufruf einen frischen Request."""

    def setUp(self):
        self.store = {
            "API": {"key": "master-key-abc"},
            "WebUI": {"api_token": "browser-token-xyz"},
            "JDownloader": {"user": "", "password": "", "device": ""},
        }
        self.app = bottle.Bottle()

        # Die echte Config liest ihren Pfad aus dem Shared State, den
        # `get_api` als erstes Argument uebernimmt. Ohne das wuerde die App
        # beim Initialisieren der Benachrichtigungen in die `kuasarr.ini` des
        # Entwicklers greifen. Der Rest der Konfiguration darf echt sein -
        # nur die Konfigurationsdatei wird entsorgt.
        self.configdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.configdir.cleanup)
        state = {
            "configfile": os.path.join(self.configdir.name, "kuasarr.ini"),
            "dbfile": os.path.join(self.configdir.name, "kuasarr.db"),
            # Die Statistik-Provider erwarten eine Factory, keine offene
            # Verbindung - jede Tabelle bekommt ihre eigene In-Memory-DB.
            "database": _FakeDatabase,
            "port": 8080,
        }

        patches = [
            patch("kuasarr.api.Config", _make_config(self.store)),
            patch("kuasarr.providers.auth.Config", _make_config(self.store)),
            patch("kuasarr.providers.ui.html_templates.Config",
                  _make_config(self.store)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        # `get_api` baut die App selbst und startet danach unbedingt den
        # Server. Fuer den Test wird der Konstruktor auf die vorbereitete
        # App umgebogen, damit die Registrierung sichtbar wird, und der
        # Server-Start durch einen Attrappen ersetzt.
        state["port"] = 8080
        with patch("kuasarr.providers.shared_state.get_db"), \
                patch("kuasarr.api.Bottle", return_value=self.app), \
                patch("kuasarr.api.Server") as server:
            # Der Server-Start ist der letzte Schritt von `get_api`; er wird
            # hier nur festgehalten, damit der Test nicht blockiert.
            from kuasarr.api import get_api
            get_api(state, _FakeLock())
        self.assertTrue(
            server.return_value.serve_forever.called,
            "get_api muss unveraendert auch den Server starten",
        )

    def call(self, path, method="GET", query="", body=b"", headers=None,
             api_key="master-key-abc"):
        """Schickt einen echten WSGI-Request durch die App.

        Bewusst nicht ``route.callback()``: der Aufruf eines Callbacks
        umgeht genau das, was diese Tests pruefen sollen - den
        ``abort()``-Pfad, die Fehlerhandler, die Hooks und die
        Statuscodes, die Bottle erst beim Verpacken setzt.

        ``api_key`` ist der Master-Key und wird wie im echten Betrieb
        als ``X-API-Key`` mitgeschickt. ``None`` schickt gar keinen -
        damit lassen sich die Auth-Pfade pruefen.
        """
        sent = dict(headers or {})
        if api_key is not None and not any(
                name.lower() in ("x-api-key", "apikey")
                for name in sent):
            sent["X-API-Key"] = api_key

        captured = {}

        def start_response(status, response_headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = response_headers
            return lambda data: None

        chunks = self.app(_environ(path, method, query, body, sent),
                          start_response)
        payload = b"".join(chunk for chunk in chunks
                           if isinstance(chunk, bytes))
        return _Response(captured["status"], captured["headers"], payload)

    def call_json(self, *args, **kwargs):
        """Wie ``call``, liefert den Body aber bereits geparst mit.

        Bleibt er leer (etwa weil die Legacy-Seite HTML liefert), ist der
        zweite Wert ``None`` - dann lohnt sich kein ``json.loads``-Fehler.
        """
        response = self.call(*args, **kwargs)
        try:
            return response, response.json()
        except (ValueError, TypeError):
            return response, None


class TestJsonErrorHandler(_ApiCase):
    """#87: API-Fehler kommen als JSON, nicht als HTML."""

    def test_unknown_api_route_answers_with_json(self):
        response, result = self.call_json("/api/gibt-es-nicht")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(result["error"]["code"], "not_found")
        self.assertTrue(result["error"]["message"])
        self.assertIn("json", response.content_type)

    def test_unknown_non_api_route_still_answers_with_html(self):
        """Ausserhalb von ``/api`` bleibt die HTML-Seite erhalten.

        Die Legacy-Seiten (``/captcha/...``, ``/packages``) erwarten HTML -
        ein pauschaler JSON-Handler wuerde sie zerstoeren. Der Statuscode
        ist hier absichtlich nicht festgeschrieben: ohne gebauten
        WebUI-Build antwortet der SPA-Catch-all mit 500 statt 404, und
        entscheidend ist allein der Inhaltstyp.
        """
        response = self.call("/gibt-es-nicht-auch-nicht")
        self.assertIn("html", response.content_type)
        self.assertNotIn("application/json", response.content_type)

    def test_missing_api_key_reaches_the_client_as_json(self):
        response, result = self.call_json("/api/statistics", api_key=None)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(result["error"]["code"], "unauthorized")
        self.assertIn("message", result["error"])

    def test_wrong_api_key_is_rejected(self):
        response, result = self.call_json(
            "/api/statistics", headers={"X-API-Key": "falsch"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(result["error"]["code"], "forbidden")

    def test_both_keys_are_accepted(self):
        """Maschinen-Key und Browser-Token gelten beide.

        Das ist der Vertrag hinter #99: der Browser traegt ein eigenes
        Token, Radarr/Sonarr weiter den Master-Key.
        """
        for key in ("master-key-abc", "browser-token-xyz"):
            with self.subTest(key=key):
                response, _ = self.call_json(
                    "/api/statistics", headers={"X-API-Key": key})
                self.assertEqual(response.status_code, 200)


class TestRegenerateApiKey(_ApiCase):
    """#91: eine zustandsaendernde Route darf kein GET sein."""

    def test_it_is_not_reachable_with_get(self):
        self.assertFalse(
            any(rule.rule == "/regenerate-api-key" and rule.method == "GET"
                for rule in self.app.routes),
            "Die Route darf nicht mehr als GET registriert sein - ein "
            "<img src=...> im LAN rotierte sonst den Master-Key.",
        )

    def test_it_is_registered_for_post(self):
        self.assertTrue(
            any(rule.rule == "/regenerate-api-key" and rule.method == "POST"
                for rule in self.app.routes)
        )

    def test_post_without_csrf_token_is_refused(self):
        response = self.call("/regenerate-api-key", method="POST")
        self.assertEqual(response.status_code, 403)
        # Die Route liegt ausserhalb von ``/api`` und antwortet daher
        # weiterhin mit HTML - der Browser zeigt die Meldung an, aber
        # entscheidend ist, dass der Key unangetastet bleibt.
        self.assertIn("CSRF", response.text)

    def test_the_key_survives_a_refused_post(self):
        self.call_json("/regenerate-api-key", method="POST")
        self.assertEqual(self.store["API"]["key"], "master-key-abc")


class TestRegenerateBrowserToken(_ApiCase):
    """#91: der Browser laesst sich entwaffnen, ohne die *arr zu trennen.

    `POST /regenerate-api-key` bricht jede Radarr/Sonarr-Integration, weil
    der Master-Key dort fuer beide steht. Nach einem XSS in der SPA ist aber
    genau das Browser-Token das, das man loswerden will - und dafuer gibt es
    jetzt eine eigene Route.
    """

    TOKEN = "csrf-token-im-test"

    def _call_with_token(self):
        return self.call(
            "/regenerate-browser-token", method="POST",
            headers={"X-CSRF-Token": self.TOKEN,
                     "Cookie": f"kuasarr_csrf={self.TOKEN}"},
        )

    def test_it_is_only_registered_for_post(self):
        methods = [rule.method for rule in self.app.routes
                   if rule.rule == "/regenerate-browser-token"]
        self.assertEqual(methods, ["POST"])

    def test_post_without_csrf_token_is_refused(self):
        response = self.call("/regenerate-browser-token", method="POST")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.store["WebUI"]["api_token"], "browser-token-xyz")

    def test_the_master_key_survives(self):
        self._call_with_token()
        self.assertEqual(self.store["API"]["key"], "master-key-abc")

    def test_only_the_browser_token_changes(self):
        self._call_with_token()
        self.assertNotEqual(self.store["WebUI"]["api_token"], "browser-token-xyz")
        self.assertTrue(self.store["WebUI"]["api_token"])

    def test_the_old_token_stops_working_afterwards(self):
        """Der Zweck der Route: das gestohlene Token ist sofort wertlos."""
        self._call_with_token()
        response, result = self.call_json(
            "/api/statistics", headers={"X-API-Key": "browser-token-xyz"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(result["error"]["code"], "forbidden")

    def test_the_new_token_works(self):
        self._call_with_token()
        response, _ = self.call_json(
            "/api/statistics",
            headers={"X-API-Key": self.store["WebUI"]["api_token"]})
        self.assertEqual(response.status_code, 200)


class TestCsrfProtection(_ApiCase):
    """#86: die Schreibpfade der WebUI verlangen ein CSRF-Token.

    Der Schutz ist erst dann wirksam, wenn Cookie und Header zusammen
    passen. Diese Tests fahren deshalb den echten WSGI-Durchlauf: ein
    Aufruf des Route-Callbacks wuerde an ``request.method`` vorbeikommen,
    weil Bottle ausserhalb einer Bindung einen leeren Request liefert -
    die Absicherung laeuft dann nie und der Test waere gruen, ohne
    etwas zu pruefen.
    """

    # Der Token, den `/api/csrf` fuer diesen Browser ausstellt.
    TOKEN = "csrf-token-im-test"

    def _cookie(self):
        return {"Cookie": f"kuasarr_csrf={self.TOKEN}"}

    def _route(self, rule, method=None):
        for candidate in self.app.routes:
            if candidate.rule == rule and (method is None
                                           or candidate.method == method):
                return candidate
        self.fail(f"Route {rule} ({method}) ist nicht registriert")

    def test_the_token_route_sets_the_cookie(self):
        """Ohne dieses Cookie gibt es nichts, womit der Header verglichen wird."""
        response = self.call("/api/csrf", api_key=None)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.text)["data"]
        self.assertTrue(payload["csrf_token"])
        set_cookie = "".join(
            value for name, value in response.headers.items()
            if name == "set-cookie"
        )
        self.assertIn("kuasarr_csrf", set_cookie)

    def test_a_post_without_a_token_is_refused(self):
        body = json.dumps({"configs": []}).encode("utf-8")
        response = self.call("/api/notifications", method="POST", body=body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(json.loads(response.text)["error"]["code"], "forbidden")

    def test_a_cookie_without_a_header_is_refused(self):
        """Das haeufigste Missverstaendnis: das Cookie allein reicht nicht."""
        body = json.dumps({"configs": []}).encode("utf-8")
        response = self.call("/api/notifications", method="POST", body=body,
                             headers=self._cookie())
        self.assertEqual(response.status_code, 403)

    def test_a_header_without_a_cookie_is_refused(self):
        """Und umgekehrt: ein geratener Header ohne Cookie auch nicht."""
        body = json.dumps({"configs": []}).encode("utf-8")
        response = self.call("/api/notifications", method="POST", body=body,
                             headers={"X-CSRF-Token": self.TOKEN})
        self.assertEqual(response.status_code, 403)

    def test_a_wrong_token_is_refused(self):
        body = json.dumps({"configs": []}).encode("utf-8")
        response = self.call(
            "/api/notifications", method="POST", body=body,
            headers={**self._cookie(), "X-CSRF-Token": "geraten"},
        )
        self.assertEqual(response.status_code, 403)

    def test_the_matching_pair_gets_through(self):
        """Gegenprobe zu den drei Tests darueber - sonst waeren sie nutzlos."""
        body = json.dumps({"configs": []}).encode("utf-8")
        response = self.call(
            "/api/notifications", method="POST", body=body,
            headers={**self._cookie(), "X-CSRF-Token": self.TOKEN},
        )
        self.assertNotEqual(response.status_code, 403, response.text)

    def test_the_test_button_is_protected_too(self):
        """Der Testknopf verschickt eine echte Nachricht - er ist ein Schreibpfad."""
        body = json.dumps({"provider": "discord", "settings": {}}).encode("utf-8")
        response = self.call("/api/notifications/test", method="POST",
                             body=body)
        self.assertEqual(response.status_code, 403)

    def test_every_csrf_protected_route_really_carries_the_decorator(self):
        """Struktur-Gegenprobe fuer die Routen, die hier nicht durchlaufbar sind.

        ``POST /api/categories`` braucht eine vollstaendige Konfiguration, um
        ueberhaupt am Dekorator vorbeizukommen. Geprueft wird deshalb die
        Route selbst: ein ``@wraps`` umgesetzter Dekorator hinterlaesst ein
        ``__wrapped__``, ein unbedeckter Callback nicht.
        """
        expected = [
            ("/api/categories", "POST"),
            ("/api/categories/<category_id>", "POST"),
            ("/api/categories/<category_id>", "DELETE"),
            ("/api/notifications", "POST"),
            ("/api/notifications/test", "POST"),
            ("/regenerate-api-key", "POST"),
            ("/regenerate-browser-token", "POST"),
        ]
        for rule, method in expected:
            with self.subTest(rule=rule, method=method):
                route = self._route(rule, method)
                self.assertEqual(route.method, method)
                self.assertTrue(
                    hasattr(route.callback, "__wrapped__"),
                    f"{rule} traegt den CSRF-Dekorator nicht",
                )


class TestBrowserToken(_ApiCase):
    """#99: der Browser bekommt nicht den Maschinen-Key."""

    def test_api_key_route_returns_the_browser_token(self):
        _, result = self.call_json("/api/key")
        self.assertEqual(result["data"]["key"], "browser-token-xyz")

    def test_api_key_route_never_returns_the_master_key(self):
        _, result = self.call_json("/api/key")
        self.assertNotEqual(result["data"]["key"], self.store["API"]["key"])

    def test_the_browser_token_is_generated_on_first_use(self):
        """Ohne hinterlegtes Token wird eines erzeugt und gespeichert.

        Sonst gaebe es nach einem frischen Start keinen Wert, mit dem die
        SPA sich ausweisen kann.
        """
        del self.store["WebUI"]["api_token"]
        _, result = self.call_json("/api/key")
        token = result["data"]["key"]
        self.assertTrue(token)
        self.assertEqual(self.store["WebUI"]["api_token"], token)
        self.assertNotEqual(token, self.store["API"]["key"])

    def test_the_generated_token_actually_works(self):
        del self.store["WebUI"]["api_token"]
        _, result = self.call_json("/api/key")
        token = result["data"]["key"]
        response, _ = self.call_json("/api/statistics",
                                     headers={"X-API-Key": token})
        self.assertEqual(response.status_code, 200)

    def test_repeated_calls_never_rotate_the_token(self):
        """Zwei Aufrufe hintereinander liefern denselben Wert.

        `Config` trägt Defaults nur nach, wenn die *Sektion* fehlt - auf einer
        Installation von vor dem Browser-Token bleibt `api_token` in einer
        vorhandenen `[WebUI]` also dauerhaft leer. Ohne Guard rotierte
        `get_browser_token()` dann bei jedem Aufruf neu, und `GET /api/key`
        haette dem Browser bei jedem Reload ein anderes Token gegeben. Das,
        was der Browser zuletzt bekommen hat, waere nur bis zum naechsten
        Reload gueltig gewesen.
        """
        del self.store["WebUI"]["api_token"]
        _, first = self.call_json("/api/key")
        _, second = self.call_json("/api/key")
        self.assertEqual(first["data"]["key"], second["data"]["key"])

    def test_parallel_first_use_rotates_only_once(self):
        """Auch im Gleichschritt gewinnt nur eine Rotation.

        Das Lock in `get_browser_token` verhindert, dass sich parallele
        Aufrufe gegenseitig das Token wegschreiben. Sonst haette der
        Aufrufer, der zuerst antwortet, ein Token in der Hand, das der
        zweite Aufruf bereits wieder ersetzt hat.
        """
        import threading

        del self.store["WebUI"]["api_token"]
        barrier = threading.Barrier(4)
        seen = []

        def fetch():
            barrier.wait()
            from kuasarr.providers.auth import get_browser_token

            seen.append(get_browser_token())

        threads = [threading.Thread(target=fetch) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(seen), 4)
        self.assertEqual(len(set(seen)), 1, f"Token rotiert mehrfach: {seen}")

    def test_a_non_ascii_key_is_rejected_with_403_not_500(self):
        """`secrets.compare_digest` verweigert Nicht-ASCII-``str``.

        Betroffen ist nicht nur der mitgeschickte Kandidat: der *gespeicherte*
        Schluessel kommt aus ``kuasarr.ini`` bzw. der Umgebung und ist
        frei waehlbar. Steht dort ein Umlaut, wirft der Vergleich einen
        ``TypeError`` - und aus einem 403 wuerde ein 500, den der Client als
        Serverfehler meldet statt als falschen Schluessel.
        """
        self.store["API"]["key"] = "master-schlüssel-äöü"
        response, result = self.call_json(
            "/api/statistics", headers={"X-API-Key": "falsch"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(result["error"]["code"], "forbidden")

    def test_a_non_ascii_key_still_authenticates(self):
        """Dasselbe in der Gegenrichtung: der richtige Key muss gelten.

        Geprueft wird der Vergleich direkt, nicht ueber HTTP: Bottle liest
        Header als Latin-1 und dekodiert sie als UTF-8 weiter (``bottle.py``
        Zeile 2331). Ein Umlaut im *Header* scheitert dort also schon vor
        unserem Code mit einem ``UnicodeDecodeError`` - das ist Bottles
        Protokollgrenze und nicht etwas, das diese Aenderung beheben kann.
        Der gespeicherte Schluessel ist davon nicht betroffen.
        """
        from kuasarr.providers.auth import _constant_time_equals

        self.assertTrue(_constant_time_equals("schlüssel-äöü", "schlüssel-äöü"))
        self.assertFalse(_constant_time_equals("schlüssel-äöü", "schlüssel-äox"))
        self.assertFalse(_constant_time_equals("", "schlüssel-äöü"))
        self.assertFalse(_constant_time_equals("schlüssel-äöü", ""))


class TestJDownloaderSave(_ApiCase):
    """#95: ein Fehlerfall war HTTP 200 und wurde als Erfolg angezeigt."""

    def test_missing_fields_return_a_client_error(self):
        response, result = self.call_json(
            "/api/jdownloader/save", method="POST", body=json.dumps({}).encode())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(result["error"]["code"], "bad_request")

    def test_invalid_email_returns_a_client_error(self):
        response, result = self.call_json(
            "/api/jdownloader/save", method="POST",
            body=json.dumps({"email": "keine-mail", "password": "p",
                             "device_name": "d"}).encode())
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", result["error"]["message"].lower())

    def test_a_failed_connection_is_a_gateway_error(self):
        """Der Upstream war nicht erreichbar - das ist kein 4xx."""
        with patch("kuasarr.providers.jdownloader.set_device", return_value=False):
            response, result = self.call_json(
                "/api/jdownloader/save", method="POST",
                body=json.dumps({"email": "a@b.de", "password": "p",
                                 "device_name": "d"}).encode())
        self.assertEqual(response.status_code, 502)
        self.assertEqual(result["error"]["code"], "bad_gateway")

    def test_nothing_is_persisted_when_the_connection_fails(self):
        """Vorher blieb ein Fehler zwar sichtbar, aber falsch gespeichert
        waere er schlimmer: Radarr/Sonarr haetten beim naechsten Start
        Credentials, die nie funktioniert haben."""
        with patch("kuasarr.providers.jdownloader.set_device", return_value=False):
            self.call_json(
                "/api/jdownloader/save", method="POST",
                body=json.dumps({"email": "a@b.de", "password": "p",
                                 "device_name": "d"}).encode())
        self.assertEqual(self.store["JDownloader"]["user"], "")
        self.assertEqual(self.store["JDownloader"]["device"], "")

    def test_success_uses_the_data_envelope(self):
        with patch("kuasarr.providers.jdownloader.set_device", return_value=True):
            response, result = self.call_json(
                "/api/jdownloader/save", method="POST",
                body=json.dumps({"email": "a@b.de", "password": "p",
                                 "device_name": "d"}).encode())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(result["data"]["success"])
        self.assertEqual(self.store["JDownloader"]["user"], "a@b.de")

    def test_an_empty_password_keeps_the_stored_one(self):
        """Das GET liefert das Passwort niemals zurueck.

        Ohne diese Regel muesste der Nutzer es bei *jedem* Speichern neu
        tippen, weil das Formular es als Pflichtfeld prueft.
        """
        self.store["JDownloader"]["password"] = "bereits-gespeichert"
        with patch("kuasarr.providers.jdownloader.set_device",
                   return_value=True) as set_device:
            self.call_json(
                "/api/jdownloader/save", method="POST",
                body=json.dumps({"email": "a@b.de", "password": "",
                                 "device_name": "d"}).encode())
        set_device.assert_called_once_with("a@b.de", "bereits-gespeichert", "d")
        self.assertEqual(self.store["JDownloader"]["password"], "bereits-gespeichert")

    def test_without_a_stored_password_an_empty_one_is_still_refused(self):
        response, result = self.call_json(
            "/api/jdownloader/save", method="POST",
            body=json.dumps({"email": "a@b.de", "password": "",
                             "device_name": "d"}).encode())
        self.assertEqual(response.status_code, 400)


class TestJDownloaderConfigGet(_ApiCase):
    def test_it_does_not_hand_out_the_stored_password(self):
        self.store["JDownloader"]["password"] = "geheim"
        _, result = self.call_json("/api/jdownloader/config",
                                   headers={"X-API-Key": "master-key-abc"})
        self.assertEqual(result["data"]["password"], "")

    def test_it_reports_whether_a_password_is_stored(self):
        """Ohne dieses Feld kann das Formular nicht unterscheiden zwischen
        "kein Passwort hinterlegt" und "Passwort nicht ausgeliefert"."""
        _, result = self.call_json("/api/jdownloader/config",
                                   headers={"X-API-Key": "master-key-abc"})
        self.assertFalse(result["data"]["password_set"])

        self.store["JDownloader"]["password"] = "geheim"
        _, result = self.call_json("/api/jdownloader/config",
                                   headers={"X-API-Key": "master-key-abc"})
        self.assertTrue(result["data"]["password_set"])

    def test_the_dead_fields_are_gone(self):
        """`auto_reconnect`/`max_downloads`/`max_speed` wurden nie gelesen.

        Sie im Formular stehen zu lassen hiesse: der Nutzer stellt etwas
        ein, das nichts bewirkt.
        """
        _, result = self.call_json("/api/jdownloader/config",
                                   headers={"X-API-Key": "master-key-abc"})
        for field in ("auto_reconnect", "max_downloads", "max_speed"):
            self.assertNotIn(field, result["data"])


class TestVersionRoute(_ApiCase):
    """#100: die Sidebar zeigte fest ``v1.0.0``."""

    def test_current_version_comes_from_version_json(self):
        with patch("kuasarr.providers.version.get_version",
                   return_value="2.0.8"):
            _, result = self.call_json("/api/version",
                                       headers={"X-API-Key": "master-key-abc"})
        self.assertEqual(result["data"]["current"], "2.0.8")

    def test_it_needs_no_network_call_by_default(self):
        """Der Aufruf darf die Sidebar nicht 10 Sekunden blockieren."""
        with patch("kuasarr.providers.version._fetch_releases") as fetch:
            _, result = self.call_json("/api/version",
                                       headers={"X-API-Key": "master-key-abc"})
        fetch.assert_not_called()
        self.assertTrue(result["data"]["current"])
        self.assertIsNone(result["data"]["latest_stable"])

    def test_refresh_looks_up_the_releases(self):
        with patch("kuasarr.providers.version.get_release_info",
                   return_value={"current": "2.0.8",
                                 "latest_stable": "2.1.0",
                                 "latest_prerelease": "2.2.0-beta.1",
                                 "releases_url": "https://example.invalid"}):
            _, result = self.call_json("/api/version", query="refresh=1",
                                       headers={"X-API-Key": "master-key-abc"})
        self.assertEqual(result["data"]["latest_stable"], "2.1.0")
        self.assertEqual(result["data"]["latest_prerelease"], "2.2.0-beta.1")

    def test_a_dead_network_does_not_break_the_sidebar(self):
        with patch("kuasarr.providers.version.get_release_info",
                   side_effect=RuntimeError("kein Netz")):
            response, result = self.call_json("/api/version", query="refresh=1",
                                             headers={"X-API-Key": "master-key-abc"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(result["data"]["current"])

    def test_an_up_to_date_install_advertises_no_update(self):
        """``update_available`` ist null, nicht die eigene Version.

        Vorher stand dort ungeprueft der Wert aus ``last_checked_version``,
        den der Update-Checker bei jedem Lauf mit ``v.<eigene Version>``
        ueberschreibt. Die Sidebar zeigte dadurch dauerhaft ein Update an,
        das es nicht gab.
        """
        from kuasarr.providers import version as version_provider

        current = version_provider.get_version()
        with patch("kuasarr.providers.version.get_release_info",
                   return_value={"current": current,
                                 "latest_stable": current,
                                 "latest_prerelease": None,
                                 "releases_url": "https://example.invalid"}):
            _, result = self.call_json("/api/version", query="refresh=1",
                                       headers={"X-API-Key": "master-key-abc"})
        self.assertIsNone(result["data"]["update_available"])

    def test_the_cached_check_does_not_claim_its_own_version(self):
        """Auch ohne Netz darf nicht die eigene Version als Update stehen."""
        from kuasarr.providers import version as version_provider

        current = version_provider.get_version()
        with patch.object(version_provider, "get_release_info") as fetch:
            _, result = self.call_json("/api/version",
                                       headers={"X-API-Key": "master-key-abc"})
        fetch.assert_not_called()
        self.assertIsNone(result["data"]["update_available"])

    def test_a_newer_release_is_reported(self):
        from kuasarr.providers import version as version_provider

        with patch("kuasarr.providers.version.get_release_info",
                   return_value={"current": version_provider.get_version(),
                                 "latest_stable": "99.0.0",
                                 "latest_prerelease": None,
                                 "releases_url": "https://example.invalid"}):
            _, result = self.call_json("/api/version", query="refresh=1",
                                       headers={"X-API-Key": "master-key-abc"})
        self.assertEqual(result["data"]["update_available"], "99.0.0")

    def test_an_older_release_is_not_reported(self):
        with patch("kuasarr.providers.version.get_release_info",
                   return_value={"current": "99.0.0",
                                 "latest_stable": "0.0.1",
                                 "latest_prerelease": None,
                                 "releases_url": "https://example.invalid"}):
            _, result = self.call_json("/api/version", query="refresh=1",
                                       headers={"X-API-Key": "master-key-abc"})
        self.assertIsNone(result["data"]["update_available"])


class TestReleaseDiscovery(unittest.TestCase):
    """Pre-Releases waren ueber ``/releases/latest`` strukturell unerreichbar."""

    RELEASES = [
        {"tag_name": "v2.2.0-beta.1", "prerelease": True},
        {"tag_name": "v2.1.0", "prerelease": False},
        {"tag_name": "v2.0.9", "prerelease": False},
    ]

    def _patched(self, releases=None):
        from kuasarr.providers import version

        return version, patch.object(
            version, "_fetch_releases",
            return_value=self.RELEASES if releases is None else releases)

    def test_latest_version_ignores_prereleases(self):
        """`newer_version_available()` darf nicht bei jedem Start
        "Update verfuegbar" schreien, nur weil ein Beta-Tag existiert."""
        version_module, p = self._patched()
        with p:
            self.assertEqual(version_module.get_latest_version(), "2.1.0")

    def test_release_info_splits_stable_and_prerelease(self):
        version_module, p = self._patched()
        with p:
            info = version_module.get_release_info()
        self.assertEqual(info["latest_stable"], "2.1.0")
        self.assertEqual(info["latest_prerelease"], "2.2.0-beta.1")

    def test_release_info_survives_a_repo_without_betas(self):
        version_module, p = self._patched([{"tag_name": "v2.1.0", "prerelease": False}])
        with p:
            info = version_module.get_release_info()
        self.assertEqual(info["latest_stable"], "2.1.0")
        self.assertIsNone(info["latest_prerelease"])

    def test_it_reads_the_list_endpoint_not_the_latest_endpoint(self):
        """``/releases/latest`` liefert per Definition nur stabile Releases."""
        version_module = __import__(
            "kuasarr.providers.version", fromlist=["_fetch_releases"])
        captured = {}

        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return [{"tag_name": "v2.1.0", "prerelease": False}]

        def fake_get(url, **kwargs):
            captured["url"] = url
            return _Resp()

        with patch.object(version_module.requests, "get", fake_get):
            version_module.get_release_info()
        self.assertIn("/releases?per_page=", captured["url"])
        self.assertNotIn("/releases/latest", captured["url"])


class TestRegenerateLogsNoSecret(unittest.TestCase):
    """#91 Nebenbefund: der neue Key stand im Klartext im Log."""

    def test_the_key_is_not_written_in_cleartext(self):
        from kuasarr.providers import shared_state as shared

        store = {}
        messages = []

        with patch.object(shared, "Config", _make_config(store)), \
                patch.object(shared, "info", messages.append):
            new_key = shared.generate_api_key()

        self.assertTrue(new_key)
        self.assertNotIn(new_key, "\n".join(messages))

    def test_the_browser_token_is_rotated_along_with_it(self):
        """Wer den Master-Key rotiert, tut das meist, weil er
        kompromittiert ist - ein stehengebliebenes Browser-Token waere
        dann weiter gueltig."""
        from kuasarr.providers import shared_state as shared

        store = {"API": {"key": "alt"}, "WebUI": {"api_token": "browser-alt"}}
        with patch.object(shared, "Config", _make_config(store)), \
                patch("kuasarr.providers.auth.Config", _make_config(store)), \
                patch.object(shared, "info", lambda *a, **k: None):
            shared.generate_api_key()

        self.assertNotEqual(store["WebUI"]["api_token"], "browser-alt")
        self.assertTrue(store["WebUI"]["api_token"])
        # Und es muss weiterhin ein gueltiger Schluessel sein.
        self.assertNotEqual(store["WebUI"]["api_token"], store["API"]["key"])


if __name__ == "__main__":
    unittest.main()