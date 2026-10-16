# -*- coding: utf-8 -*-
"""Container mit Mirror-Links müssen trotzdem entschlüsselt werden.

Ein Container mit Mirror-Links (``<a href="...?mirror=0">``) produzierte auf der
Instanz::

    Captcha check: CNL form present=True
    Filecrypt solved check: container div present=True
    Click'n'Load not found! Falling back to DLC...
    DLC not found! Falling back to Circle-Captcha buttons...
    Click'n'Load not found! Falling back to DLC...
    DLC not found! Falling back to Circle-Captcha buttons...
    No links found in Filecrypt response!

Die Meldung erscheint zweimal, weil die Mirror-Schleife zweimal durchlief. Die
Schleife holte per GET jede Mirror-Seite und *ersetzte* damit ``soup``. Eine
solche Mirror-Seite wird aber wieder vom Proof-of-Work-Gate beantwortet: sie hat
kein ``cnlform``. Darauf liefert ``soup.find("form", {"class": "cnlform"})``
``None``, dessen ``.get('onsubmit')`` ein ``AttributeError`` wirft - und das
nackte ``except:`` meldet das als "Click'n'Load not found!".

Damit wurde die einzige Seite, die den Payload traegt, weggeworfen und nie
entschlüsselt. Live am Container B39DCEFB58 belegt: die behaltene Seite
entschlüsselt 278 Links, die Mirror-Seiten keinen einzigen.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests
from bs4 import BeautifulSoup

from kuasarr.providers.captcha.dbc_dispatcher import (
    DBCDispatcher,
    _filecrypt_page_richness,
)

CONTAINER_URL = "https://filecrypt.cc/Container/B39DCEFB58.html"
TITLE = "American.Horror.Story.S13.GERMAN.EAC3D.DL.2160p"


def _solved_page(mirror_count=2):
    """A solved container page that also advertises mirrors."""
    mirrors = "".join(
        f'<a href="/Container/B39DCEFB58.html?mirror={i}">Mirror {i}</a>'
        for i in range(mirror_count)
    )
    return (
        '<html><body><div class="container">'
        f'{mirrors}'
        '<input type="hidden" name="hidden_cnl_id" value="SEC" />'
        '<form class="cnlform" onsubmit="try { CNLPOP(\'CID\', \'SECRET\', '
        '\'CRYPTED\', \'Some Release\'); }"></form>'
        '<button class="dlcdownload" onclick="dlc(\'X\')"></button>'
        '<a class="external_link">rapidgator</a>'
        "</div></body></html>"
    )


def _gate_page():
    """What a mirror GET returns: the proof-of-work gate, no payload form."""
    return (
        '<html><body><div class="pow-captcha">'
        "<form action='/pow' method='post'></form>"
        "<button>Bitte warten</button>"
        "</div></body></html>"
    )


class _Response:
    def __init__(self, text, url=CONTAINER_URL):
        self.status_code = 200
        self.text = text
        self.url = url


class _Session:
    """Serves the gate page for every mirror GET, as the live site does."""

    max_redirects = 5

    def __init__(self, mirror_page):
        self.mirror_page = mirror_page
        self.mirror_gets = []
        self.cookies = requests.cookies.RequestsCookieJar()

    def get(self, url, headers=None, **kwargs):
        self.mirror_gets.append(url)
        return _Response(self.mirror_page, url)

    def post(self, url, **kwargs):
        return _Response("", url)


class TestFilecryptPageRichness(unittest.TestCase):
    def test_a_page_with_the_payload_form_outranks_everything(self):
        self.assertEqual(
            _filecrypt_page_richness(BeautifulSoup(_solved_page(), "html.parser")),
            1000,
        )

    def test_the_gate_page_scores_below_the_solved_page(self):
        gate = _filecrypt_page_richness(BeautifulSoup(_gate_page(), "html.parser"))
        solved = _filecrypt_page_richness(BeautifulSoup(_solved_page(), "html.parser"))
        self.assertLess(gate, solved)

    def test_a_gate_page_with_decoy_markup_still_loses(self):
        """The gate keeps page chrome around; that must not outweigh the form."""
        gate = _gate_page().replace(
            "<button>Bitte warten</button>",
            '<a class="external_link">x</a><button class="dlcdownload"></button>'
            "<button>Bitte warten</button>",
        )
        self.assertLess(
            _filecrypt_page_richness(BeautifulSoup(gate, "html.parser")),
            _filecrypt_page_richness(BeautifulSoup(_solved_page(), "html.parser")),
        )


class TestMirrorPagesDoNotDiscardTheSolvedPage(unittest.TestCase):
    """The production symptom: a solved container with mirrors yields nothing."""

    def _extract(self, mirror_page, session=None):
        session = session or _Session(mirror_page)
        dispatcher = DBCDispatcher(
            state_module=SimpleNamespace(values={"user_agent": "test-agent"})
        )
        soup = BeautifulSoup(_solved_page(), "html.parser")
        result = dispatcher._extract_filecrypt_links(
            session, soup, CONTAINER_URL, TITLE, {"User-Agent": "test-agent"}
        )
        return result, session

    def test_links_are_still_decrypted_when_mirrors_return_the_gate(self):
        links = ["https://rapidgator.net/file/aaa", "https://rapidgator.net/file/bbb"]

        with patch("kuasarr.providers.captcha.dbc_dispatcher.CNL") as cnl:
            cnl.return_value.decrypt.return_value = links
            result, session = self._extract(_gate_page())

        self.assertIsNotNone(
            result,
            "a solved page must not be discarded just because mirrors exist",
        )
        self.assertEqual(result.get("links"), links)

    def test_the_mirror_pages_are_actually_fetched(self):
        """Otherwise this test would pass without exercising the mirror path."""
        with patch("kuasarr.providers.captcha.dbc_dispatcher.CNL") as cnl:
            cnl.return_value.decrypt.return_value = ["https://rapidgator.net/file/a"]
            _, session = self._extract(_gate_page())

        self.assertEqual(len(session.mirror_gets), 2)
        self.assertTrue(all("mirror=" in u for u in session.mirror_gets))

    def test_the_circle_captcha_fallback_is_not_taken(self):
        """The fallback chain is the symptom: it must not appear at all."""
        links = ["https://rapidgator.net/file/a"]
        with patch("kuasarr.providers.captcha.dbc_dispatcher.CNL") as cnl, \
             patch("kuasarr.providers.captcha.dbc_dispatcher.DLC") as dlc, \
             patch("kuasarr.providers.captcha.dbc_dispatcher.info") as log:
            cnl.return_value.decrypt.return_value = links
            result, _ = self._extract(_gate_page())

        self.assertEqual(result.get("links"), links)
        dlc.assert_not_called()
        said = [call.args[0] for call in log.call_args_list]
        self.assertNotIn("DLC not found! Falling back to Circle-Captcha buttons...", said)
        for message in said:
            self.assertNotIn("Circle-Captcha required", message)

    def test_the_production_log_chain_does_not_occur(self):
        """Exactly what the instance printed for a container with mirrors."""
        with patch("kuasarr.providers.captcha.dbc_dispatcher.CNL") as cnl, \
             patch("kuasarr.providers.captcha.dbc_dispatcher.info") as log:
            cnl.return_value.decrypt.return_value = ["https://rapidgator.net/file/a"]
            self._extract(_gate_page())

        said = [call.args[0] for call in log.call_args_list]
        self.assertNotIn("Click'n'Load not found! Falling back to DLC...", said)

    def test_a_container_without_mirrors_still_works(self):
        links = ["https://rapidgator.net/file/ccc"]
        session = _Session(_gate_page())
        dispatcher = DBCDispatcher(
            state_module=SimpleNamespace(values={"user_agent": "test-agent"})
        )
        soup = BeautifulSoup(_solved_page(mirror_count=0), "html.parser")

        with patch("kuasarr.providers.captcha.dbc_dispatcher.CNL") as cnl:
            cnl.return_value.decrypt.return_value = links
            result = dispatcher._extract_filecrypt_links(
                session, soup, CONTAINER_URL, TITLE, {"User-Agent": "test-agent"}
            )

        self.assertEqual(result.get("links"), links)
        self.assertEqual(session.mirror_gets, [], "no mirrors, no requests")


if __name__ == "__main__":
    unittest.main()