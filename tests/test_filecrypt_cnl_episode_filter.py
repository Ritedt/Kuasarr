# -*- coding: utf-8 -*-
"""Der CNL-Episodenfilter darf den CNL-Pfad nicht zerstören.

``/_CNL/<secret>.html?season=&episode=`` ist ein *optionaler* Filter auf den
Payload, der bereits im cnlform der Seite steht. Auf der live getesteten Seite
antwortet der Endpunkt aber fuer jede Episode und jeden Container mit HTTP 200
und einem leeren Body::

    POST https://filecrypt.cc/_CNL/1430C58BDB.html?season=17&episode=1
    -> HTTP 200, 0 bytes

Der Code hat ``status_code == 200`` als Erfolg gewertet und dann
``json.loads("")`` aufgerufen. Das ``JSONDecodeError`` landete im nackten
``except:``, das den ganzen CNL-Zweig umschliesst, und wurde gemeldet als::

    Click'n'Load not found! Falling back to DLC...
    DLC not found! Falling back to Circle-Captcha buttons...

Der Container durchlaeuft damit DLC und Circle-Captcha fuer ein Captcha, das
er gar nicht hat, obwohl der Payload zwei Zeilen zuvor fehlerfrei gelesen
wurde. Genau das war die Ursache dafuer, dass Kuasarr an jedem
Mehr-Episoden-Container ein Circle-Captcha loesen wollte.

Die Tests decken beide Implementierungen ab - den Dispatcher und den manuellen
WebUI-Pfad -, weil sie denselben Fehler getrennt enthielten.
"""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests
from bs4 import BeautifulSoup

from kuasarr.downloads.linkcrypters.filecrypt import (
    CNL,
    narrow_cnl_payload,
    get_filecrypt_links,
)
from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher

CONTAINER_URL = "https://filecrypt.cc/Container/1AAE0F1834.html"
TITLE = "American.Dad.S17E01.German.AC3D.DL.1080p"

# The three payload fields the CNL decryptor actually consumes. Values are
# opaque; only their identity matters here.
PAYLOAD = ["CID", "SECRET", "CRYPTED_LINKS", TITLE]


def _cnl_page(secret="1430C58BDB"):
    """A solved container with dlpart, so season/episode are both set."""
    return (
        '<html><body><div class="container">'
        '<div class="dlpart"><div id="selbox_season"></div>'
        '<div id="selbox_episode"></div></div>'
        f'<input type="hidden" name="hidden_cnl_id" value="{secret}" />'
        "<form class=\"cnlform\" onsubmit=\"try { CNLPOP('CID', 'SECRET', "
        "'CRYPTED_LINKS', 'American.Dad.S17 - filecrypt.cc'); }\"></form>"
        '<button class="dlcdownload" onclick="dlc(\'X\')"></button>'
        "</div></body></html>"
    )


class _Response:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class _SolvedResponse:
    """A FlareSolverr-style response already past the gate."""

    def __init__(self, html):
        self.status_code = 200
        self.text = html
        self.url = CONTAINER_URL


class _EmptyFilterSession:
    """A session whose /_CNL/ answers 200 with an empty body, as FileCrypt does."""

    max_redirects = 5

    def __init__(self, response=None):
        self.posted = []
        self.cookies = requests.cookies.RequestsCookieJar()
        self._response = response if response is not None else _Response(200, "")

    def post(self, url, headers=None, **kwargs):
        self.posted.append(url)
        return self._response

    def get(self, url, **kwargs):
        raise AssertionError("the CNL branch must not fall through to a GET")


class TestNarrowCnlPayloadKeepsPayloadOnEmptyAnswer(unittest.TestCase):
    """The filter is optional, so a failed filter returns the payload."""

    def _narrow(self, session, season="season=17", episode="episode=1"):
        return narrow_cnl_payload(
            session, CONTAINER_URL, {"User-Agent": "test-agent"},
            "1430C58BDB", season, episode, list(PAYLOAD), TITLE,
        )

    def test_empty_body_leaves_the_payload_untouched(self):
        """This is the live behaviour: HTTP 200, zero bytes."""
        self.assertEqual(self._narrow(_EmptyFilterSession()), PAYLOAD)

    def test_non_json_body_leaves_the_payload_untouched(self):
        session = _EmptyFilterSession(_Response(200, "<html>blocked</html>"))
        self.assertEqual(self._narrow(session), PAYLOAD)

    def test_json_without_success_leaves_the_payload_untouched(self):
        session = _EmptyFilterSession(_Response(200, json.dumps({"error": "nope"})))
        self.assertEqual(self._narrow(session), PAYLOAD)

    def test_a_failing_request_leaves_the_payload_untouched(self):
        class _Boom:
            def post(self, url, headers=None, **kwargs):
                raise requests.ConnectionError("connection reset")
        self.assertEqual(self._narrow(_Boom()), PAYLOAD)

    def test_a_missing_secret_skips_the_request_entirely(self):
        session = _EmptyFilterSession()
        self.assertEqual(
            narrow_cnl_payload(session, CONTAINER_URL, {}, None,
                               "season=17", "episode=1", list(PAYLOAD), TITLE),
            PAYLOAD,
        )
        self.assertEqual(session.posted, [], "no secret means no request to make")

    def test_a_working_filter_still_narrows_the_payload(self):
        """The fix must not disable a filter that FileCrypt does answer."""
        filtered = json.dumps({
            "success": True,
            "data": ["NARROWED_CID", "NARROWED_SECRET", "IGNORED", "IGNORED"],
        })
        session = _EmptyFilterSession(_Response(200, filtered))

        result = self._narrow(session)

        self.assertEqual(
            result,
            ["CID", "NARROWED_CID", "NARROWED_SECRET", TITLE],
        )


class TestDispatcherDoesNotAbandonCnlForAFailedFilter(unittest.TestCase):
    """The production symptom: DLC and Circle-Captcha for a solved container."""

    def _extract(self, session):
        dispatcher = DBCDispatcher(
            state_module=SimpleNamespace(values={"user_agent": "test-agent"})
        )
        soup = BeautifulSoup(_cnl_page(), "html.parser")
        return dispatcher._extract_filecrypt_links(
            session, soup, CONTAINER_URL, TITLE, {"User-Agent": "test-agent"}
        )

    def test_an_empty_filter_answer_still_decrypts_the_links(self):
        decrypted = ["https://rapidgator.net/file/aaa"]

        with patch.object(CNL, "decrypt", return_value=decrypted):
            result = self._extract(_EmptyFilterSession())

        self.assertIsNotNone(
            result,
            "the container must not be routed into the Circle-Captcha fallback",
        )
        self.assertEqual(result.get("links"), decrypted)

    def test_dlc_is_never_reached(self):
        """DLC was the step that reported the failure and burned a round-trip."""
        with patch.object(CNL, "decrypt", return_value=["https://rapidgator.net/file/aaa"]), \
             patch("kuasarr.providers.captcha.dbc_dispatcher.DLC") as dlc:
            self._extract(_EmptyFilterSession())

        dlc.assert_not_called()

    def test_the_manual_webui_path_behaves_the_same(self):
        """The same bug lived here a second time, independently."""
        state = SimpleNamespace(values={"user_agent": "test-agent"})
        # A real Session so the origin guard can wrap it; only the /_CNL/ POST
        # is stubbed, because that is the request under test.
        session = requests.Session()
        posted = []

        def fake_post(url, **kwargs):
            posted.append(url)
            return _Response(200, "")

        with patch("kuasarr.downloads.linkcrypters.filecrypt.requests.Session",
                   return_value=session), \
             patch("kuasarr.downloads.linkcrypters.filecrypt.ensure_session_cf_bypassed",
                   side_effect=lambda info, st, sess, url, headers:
                       (sess, headers, _SolvedResponse(_cnl_page()))), \
             patch.object(session, "post", side_effect=fake_post), \
             patch.object(CNL, "decrypt", return_value=["https://rapidgator.net/file/aaa"]):
            links = get_filecrypt_links(state, "token", TITLE, CONTAINER_URL)

        self.assertEqual(
            links.get("links"), ["https://rapidgator.net/file/aaa"],
            "the manual path lost the container to the same empty filter answer",
        )
        self.assertTrue(
            any("/_CNL/" in u for u in posted),
            "the episode filter never ran, so this test proves nothing",
        )


if __name__ == "__main__":
    unittest.main()