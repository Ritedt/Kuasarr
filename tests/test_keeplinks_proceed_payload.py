# -*- coding: utf-8 -*-
"""Tests fuer den Keeplinks-'Click To Proceed'-POST.

Der Proceed-Schritt schickte zuvor nicht nur das noetige showpageval,
sondern das komplette Formular zurueck. Auf der Keeplinks-Containerseite
heisst das, dass ein leeres ``captcha_cool`` gemeinsam mit ``hiddencaptcha=1``
und ``captchatype`` mitgeht, obwohl noch gar keine Antwort gegeben wurde. Die
Referenzimplementierung schickt ausschliesslich ``showpageval=1``; genau das
wird hier festgeschrieben.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from kuasarr.downloads.linkcrypters.keeplinks import get_keeplinks_links
from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher

CONTAINER_URL = "https://www.keeplinks.org/p26/6aa36f6b8697a"

# Die reale Containerseite vor dem Proceed-Klick: frmprotect mit showpageval=1
# und - weil das Formular das komplette Antwortfeld mitliefert - bereits allen
# Captcha-Feldern. Genau das Formular, das vorher komplett weitergereicht wurde.
PROCEED_PAGE_HTML = (
    "<html><body>"
    "<form name='frmprotect' method='post' "
    "action='https://www.keeplinks.org/p26/6aa36f6b8697a'>"
    "<input type='hidden' name='showpageval' value='1'>"
    "<input type='hidden' name='myhiddenpwd' value=''>"
    "<input type='hidden' name='kl_ab' value='0'>"
    "<input type='submit' name='hbtncheck' value=''>"
    "<input type='hidden' name='hiddenaction' value='Q2hlY2tJbmZv'>"
    "<input type='hidden' name='captchatype' value='Cool'>"
    "<input type='hidden' name='hiddencaptcha' value='1'>"
    "<input type='hidden' name='hiddenpwd' value=''>"
    "<input type='text' name='captcha_cool' value=''>"
    "</form>"
    "</body></html>"
)

# Antwort auf den Proceed-POST: Container ist offen, der Download steht im
# trurl-Textarea. Damit endet der Test ohne Captcha-Solving.
UNLOCKED_PAGE_HTML = (
    "<html><body><textarea class='trurl'>"
    "https://rapidgator.net/file/abcdef123"
    "</textarea></body></html>"
)


class _FakeResponse:
    """Minimaler Response-Ersatz - nur .text/.content werden gebraucht."""

    def __init__(self, text, content=b"", status_code=200):
        self.text = text
        self.content = content or text.encode()
        self.status_code = status_code


class ProceedPayloadTest(unittest.TestCase):
    """Der Proceed-POST darf nur showpageval=1 schicken."""

    def _dispatcher(self):
        return DBCDispatcher(state_module=SimpleNamespace(values={
            "user_agent": "Kuasarr-Test",
        }))

    def _session_returning(self, *pages):
        """Session-Mock, der bei jedem GET die naechste Seite liefert."""
        session = MagicMock()
        responses = [_FakeResponse(page) for page in pages]
        session.get.side_effect = responses
        session.post.return_value = _FakeResponse(UNLOCKED_PAGE_HTML)
        return session

    def test_dispatcher_proceed_post_sends_only_showpageval(self):
        """Dispatcher-Pfad: der Proceed-POST traegt genau ein Feld."""
        dispatcher = self._dispatcher()
        session = self._session_returning(PROCEED_PAGE_HTML)

        with unittest.mock.patch.object(dispatcher, "_same_origin_guard_for",
                                       return_value=session):
            dispatcher._solve_keeplinks_with_dbc("Titel", CONTAINER_URL, None)

        self.assertTrue(session.post.called, "Proceed-POST wurde nicht abgesetzt")
        _, kwargs = session.post.call_args
        self.assertEqual(kwargs["data"], {"showpageval": "1"})

    def test_proceed_post_omits_captcha_fields(self):
        """Das leere captcha_cool darf das Formular nicht mehr verlassen."""
        dispatcher = self._dispatcher()
        session = self._session_returning(PROCEED_PAGE_HTML)

        with unittest.mock.patch.object(dispatcher, "_same_origin_guard_for",
                                       return_value=session):
            dispatcher._solve_keeplinks_with_dbc("Titel", CONTAINER_URL, None)

        _, kwargs = session.post.call_args
        sent = set(kwargs["data"])
        self.assertNotIn("captcha_cool", sent)
        self.assertNotIn("hiddencaptcha", sent)
        self.assertNotIn("captchatype", sent)

    def test_webui_path_proceed_post_sends_only_showpageval(self):
        """Auch der WebUI-Pfad schickt nur showpageval=1."""
        shared_state = SimpleNamespace(values={"user_agent": "Kuasarr-Test"})
        with unittest.mock.patch("kuasarr.downloads.linkcrypters.keeplinks.requests.Session") as factory:
            session = factory.return_value
            session.get.return_value = _FakeResponse(PROCEED_PAGE_HTML)
            session.post.return_value = _FakeResponse(UNLOCKED_PAGE_HTML)

            get_keeplinks_links(shared_state, "antwort", "Titel", CONTAINER_URL)

        self.assertTrue(session.post.called, "Proceed-POST wurde nicht abgesetzt")
        _, kwargs = session.post.call_args
        self.assertEqual(kwargs["data"], {"showpageval": "1"})
        self.assertNotIn("captcha_cool", kwargs["data"])


if __name__ == "__main__":
    unittest.main()