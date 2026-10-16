# -*- coding: utf-8 -*-
"""Resilienz-Tests für den DBC-Dispatcher.

Zwei Fehler steckten beide in ``dbc_dispatcher.py``:

1. Der Circle-Skip-POST in ``_solve_filecrypt_with_dbc`` lief ohne ``timeout``.
   Weil der Dispatcher single-threaded läuft (``max_concurrent = 1``), friert
   ein hängender POST die gesamte Queue ein.
2. Der nackte ``except Exception`` in ``_solve_circle_captcha`` schluckte auch
   ``DBCInsufficientCredits`` und ``DBCServiceOverload``. Beide erben von
   ``RuntimeError``, also von ``Exception`` - der Backoff in ``_run_once``
   bekam sie dadurch nie zu sehen.

Die Tests brauchen weder Netzwerk noch den Dispatcher-Thread: HTTP läuft über
MagicMock-Sessions, der Client über einen MagicMock.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

from kuasarr.providers.captcha.base_client import (
    CaptchaInsufficientCredits,
    CaptchaServiceOverload,
)
from kuasarr.providers.captcha.dbc_client import (
    DBCInsufficientCredits,
    DBCServiceOverload,
)
from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher

CONTAINER_URL = "https://filecrypt.cc/Container/468F7D93BA.html"

# Seite ohne CNL-Form, aber mit Circle-Captcha - der Zustand, in dem der
# Skip-POST aus Issue #76 hängt.
CIRCLE_PAGE_HTML = (
    "<html><head><title>Filecrypt</title></head><body>"
    "<div class=\"container\">"
    "<div class=\"circle_captcha\">"
    "<img src=\"https://filecrypt.cc/captcha/x.png\">"
    "</div>"
    "</div></body></html>"
)


# Antwort auf den Skip-POST: das Circle-Captcha ist weg, der Container ist offen.
# Damit endet der Skip-Loop nach dem ersten Versuch und der cap_token-POST folgt.
NO_CIRCLE_PAGE_HTML = (
    "<html><head><title>Filecrypt</title></head>"
    "<body><div class=\"container\">"
    "<div class=\"dlpart\">"
    "<a href=\"https://rapidgator.net/file/abc\" class=\"ln\">rapidgator</a>"
    "</div></div></body></html>"
)


class _FakeResponse:
    """Minimaler Response-Ersatz - der Dispatcher braucht nur drei Attribute."""

    def __init__(self, text, url=CONTAINER_URL, status_code=200, content=b"PNG"):
        self.text = text
        self.url = url
        self.status_code = status_code
        self.content = content
        self.ok = True


def _make_dispatcher():
    state_module = SimpleNamespace(values={"user_agent": "test-agent"})
    return DBCDispatcher(state_module=state_module)


def _circle_captcha_session():
    """Gefälschte Session, deren GET eine Circle-Captcha-Seite liefert."""
    session = MagicMock()
    session.get.return_value = _FakeResponse(CIRCLE_PAGE_HTML)
    return session


class TestSolveCircleCaptchaLetsServiceErrorsThrough(unittest.TestCase):
    """Issue #75 - Kredit- und Überlastungsfehler müssen _run_once erreichen."""

    def _run_with_client_error(self, error):
        dispatcher = _make_dispatcher()
        dispatcher._client = MagicMock()
        dispatcher._client.solve_coordinates_captcha.side_effect = error
        session = _circle_captcha_session()

        with patch.object(DBCDispatcher, "_same_origin_guard_for", return_value=session), \
                patch("kuasarr.providers.captcha.dbc_dispatcher.time.sleep"):
            dispatcher._solve_circle_captcha(
                title="Some.Release",
                url=CONTAINER_URL,
                phpsessid="abc123",
                password="",
            )

    def test_insufficient_credits_is_re_raised(self):
        """Ohne das Re-Raisen verschwindet der Fehler im Broad-Except."""
        with self.assertRaises(DBCInsufficientCredits):
            self._run_with_client_error(DBCInsufficientCredits("no credits left"))

    def test_service_overload_is_re_raised(self):
        with self.assertRaises(DBCServiceOverload):
            self._run_with_client_error(DBCServiceOverload("service overloaded"))

    def test_captcha_client_variants_are_re_raised_too(self):
        """Auch die 2Captcha-Klassen sind RuntimeError-Nachfahren."""
        with self.assertRaises(CaptchaInsufficientCredits):
            self._run_with_client_error(CaptchaInsufficientCredits("no credits left"))

        with self.assertRaises(CaptchaServiceOverload):
            self._run_with_client_error(CaptchaServiceOverload("service overloaded"))

    def test_ordinary_request_error_is_still_retried(self):
        """Ein gewöhnlicher Netzwerkfehler darf die Schleife nicht abbrechen."""
        dispatcher = _make_dispatcher()
        dispatcher._client = MagicMock()
        dispatcher._client.solve_coordinates_captcha.side_effect = requests.RequestException("boom")
        session = _circle_captcha_session()

        with patch.object(DBCDispatcher, "_same_origin_guard_for", return_value=session), \
                patch("kuasarr.providers.captcha.dbc_dispatcher.time.sleep"):
            result = dispatcher._solve_circle_captcha(
                title="Some.Release",
                url=CONTAINER_URL,
                phpsessid="abc123",
                password="",
            )

        self.assertIsNone(result, "Der Retrying-Pfad kehrt regulär None zurück")
        self.assertEqual(
            dispatcher._client.solve_coordinates_captcha.call_count, 3,
            "Ein gewöhnlicher Fehler muss alle drei Versuche durchlaufen",
        )


class TestFilecryptNetworkCallsAreBounded(unittest.TestCase):
    """Issue #76 - kein Netzwerkaufruf im Filecrypt-Pfad darf unbegrenzt haengen.

    Die Aussage dieser Tests hat sich mit dem Code verschoben, nicht ihre
    Absicht. Frueher prueften sie den "Circle-Skip"-Loop, der drei
    Zufallskoordinaten an /captcha/circle.php schickte. Der Pfad existiert
    nicht mehr: er wurde durch echtes Bild-Solving ersetzt (Bild an DBC,
    zurueckkommende (x, y) klicken). Zufallskoordinaten konnten das Captcha
    gar nicht loesen.

    Der Dispatcher laeuft single-threaded (max_concurrent = 1). Ein einziger
    haengender Aufruf friert deshalb die komplette Queue ein. Die Haenge-
    Absicht von #76 gilt fuer jeden Aufruf im Pfad, also wird sie hier gegen
    den Quelltext des Pfades geprueft statt gegen einen Weg, den es nicht
    mehr gibt.
    """

    FILECRYPT_METHOD = "_solve_filecrypt_with_dbc"

    def _filecrypt_source(self):
        import inspect
        from kuasarr.providers.captcha import dbc_dispatcher as mod
        return inspect.getsource(getattr(mod.DBCDispatcher, self.FILECRYPT_METHOD))

    def test_no_unbounded_session_call_in_the_filecrypt_path(self):
        """Jeder session.get/post im Filecrypt-Pfad braucht einen timeout.

        Geprueft wird der Quelltext des Pfades: das ist unabhaengig davon,
        ob der Test gerade einen bestimmten Antwort-Baum durchlaeuft, und
        deckt auch Zweige ab, die spaeter dazukommen.
        """
        import re
        source = self._filecrypt_source()
        calls = re.findall(r"session\.(?:get|post)\(", source)
        self.assertTrue(calls, "Kein session-Aufruf gefunden - Test prueft nichts")

        for match in re.finditer(r"session\.(?:get|post)\((?:[^()]|\([^()]*\))*", source):
            call = match.group(0)
            self.assertIn(
                "timeout=", call,
                f"Dieser Aufruf kann unbegrenzt haengen (Issue #76): {call}",
            )

    def test_circle_image_fetch_is_bounded(self):
        """Das Circle-Bild wird mit Timeout geladen - es ist ein HTTP-Aufruf."""
        import re
        source = self._filecrypt_source()
        img_fetch = [m.group(0) for m in re.finditer(
            r"session\.get\((?:[^()]|\([^()]*\))*", source
        )]
        for call in img_fetch:
            if "captcha/circle" in call or "img_url" in call or "img_src" in call:
                self.assertIn("timeout=", call,
                              f"Der Circle-Bildabruf braucht einen Timeout: {call}")

    def test_a_hanging_coordinate_post_is_bounded(self):
        """Der Klick auf die zurueckgegebenen Koordinaten ist ebenfalls begrenzt."""
        import re
        source = self._filecrypt_source()
        click_post = [m.group(0) for m in re.finditer(
            r"session\.post\((?:[^()]|\([^()]*\))*", source
        )]
        for call in click_post:
            if "button.x=" in call:
                self.assertIn("timeout=", call,
                              f"Der Koordinaten-POST braucht einen Timeout: {call}")


if __name__ == "__main__":
    unittest.main()