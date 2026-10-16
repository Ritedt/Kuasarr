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


class TestCircleSkipPostSetsTimeout(unittest.TestCase):
    """Issue #76 - der Circle-Skip-POST hing ohne timeout auf requests."""

    def _run_skip_path(self, post_side_effect):
        dispatcher = _make_dispatcher()
        session = MagicMock()
        session.post.side_effect = post_side_effect

        with patch(
            "kuasarr.providers.captcha.dbc_dispatcher.ensure_session_cf_bypassed",
            return_value=(session, {"User-Agent": "test-agent"},
                          _FakeResponse(CIRCLE_PAGE_HTML)),
        ), patch(
            "kuasarr.providers.captcha.dbc_dispatcher._same_origin_guard_for",
            return_value=session,
        ), patch.object(
            dispatcher, "_get_captcha_token", return_value=None
        ):
            dispatcher._solve_filecrypt_with_dbc(
                title="Some.Release",
                url=CONTAINER_URL,
                password="",
            )
        return session

    def test_skip_post_passes_a_timeout(self):
        """Der Timeout ist die Eigenschaft, nicht die konkrete Sekundenzahl."""
        session = self._run_skip_path([_FakeResponse(CIRCLE_PAGE_HTML)] * 3)

        self.assertTrue(session.post.call_args_list, "Der Circle-Skip-POST lief nie")
        for call in session.post.call_args_list:
            kwargs = call.kwargs
            self.assertIsNotNone(
                kwargs.get("timeout"),
                f"Der Circle-Skip-POST wurde ohne timeout aufgerufen: {kwargs}",
            )

    def test_timeout_leaves_the_loop_instead_of_escaping(self):
        """Ein Timeout darf nicht aus der Methode herausfliegen."""
        session = self._run_skip_path(requests.ReadTimeout("timed out"))

        self.assertEqual(
            session.post.call_count, 1,
            "Der Timeout muss den Retry-Loop kontrolliert verlassen, nicht propagieren",
        )

    def test_repeated_timeouts_never_loop_forever(self):
        session = self._run_skip_path(requests.ReadTimeout("timed out"))

        self.assertLessEqual(
            session.post.call_count, 3,
            "Der Skip-Loop ist bei drei Versuchen gedeckelt",
        )

    def test_healthy_circle_page_stays_capped_at_three_attempts(self):
        """Ohne Timeout ist die Drei-Versuche-Grenze die einzige Bremse."""
        session = self._run_skip_path([_FakeResponse(CIRCLE_PAGE_HTML)] * 5)

        self.assertEqual(
            session.post.call_count, 3,
            "Der Skip-Loop darf höchstens dreimal posten",
        )

    def test_every_post_in_the_filecrypt_path_has_a_timeout(self):
        """Auch der cap_token-POST darf nicht unbegrenzt hängen."""
        dispatcher = _make_dispatcher()
        session = MagicMock()
        # Erst der Skip-POST, danach der cap_token-POST.
        session.post.side_effect = [
            _FakeResponse(NO_CIRCLE_PAGE_HTML),
            _FakeResponse(NO_CIRCLE_PAGE_HTML),
        ]

        with patch(
            "kuasarr.providers.captcha.dbc_dispatcher.ensure_session_cf_bypassed",
            return_value=(session, {"User-Agent": "test-agent"},
                          _FakeResponse(CIRCLE_PAGE_HTML)),
        ), patch(
            "kuasarr.providers.captcha.dbc_dispatcher._same_origin_guard_for",
            return_value=session,
        ), patch.object(
            dispatcher, "_get_captcha_token", return_value="the-token"
        ):
            dispatcher._solve_filecrypt_with_dbc(
                title="Some.Release",
                url=CONTAINER_URL,
                password="",
            )

        self.assertEqual(session.post.call_count, 2)
        for call in session.post.call_args_list:
            self.assertIsNotNone(call.kwargs.get("timeout"))


if __name__ == "__main__":
    unittest.main()