# -*- coding: utf-8 -*-
"""Tests fuer die Link-Extraktion aus dem trurl-Textarea.

Keeplinks rendert die Downloads eines geoeffneten Containers in ein
``<textarea class="trurl">``, eine URL pro Zeile. Diese Quelle wurde gar nicht
gelesen - gesucht wurden nur ``<a href>``. Wenn ein Container-Layout keine
erkennbaren Anker liefert, meldete Kuasarr "No download links found",
obwohl die Links die ganze Zeit im HTML standen.

Bewusst ohne Hoster-Filter: Kuasarr buendelt per Vorgabe keine Hoster-Namen,
und das Textarea sagt verbindlich, was hinter dem Container liegt. Verworfen
werden nur Leerzeilen und Text, der keine URL ist.
"""

import unittest
from types import SimpleNamespace

from bs4 import BeautifulSoup

from kuasarr.downloads.linkcrypters.keeplinks import extract_download_links
from kuasarr.providers.captcha.dbc_dispatcher import DBCDispatcher


def _soup(html):
    return BeautifulSoup(html, "html.parser")


TRURL_PAGE = (
    "<html><body>"
    "<textarea class='trurl'>\n"
    "https://rapidgator.net/file/aaaa1111\n"
    "https://ddownload.com/bbbb2222/film.mkv\n"
    "</textarea>"
    "</body></html>"
)

# Layout ohne Textarea, aber mit den ueblichen Ankern.
ANCHOR_PAGE = (
    "<html><body>"
    "<label class='form_box_title'>"
    "<a class='selecttext' href='https://rapidgator.net/file/cccc3333'>DL</a>"
    "</label>"
    "</body></html>"
)

# Textarea mit Muell: Leerzeilen, ein Kommentar, ein nicht-HTTP-Eintrag.
TRURL_MESSY_PAGE = (
    "<html><body>"
    "<textarea class='trurl'>\n"
    "\n"
    "   \n"
    "https://rapidgator.net/file/dddd4444\n"
    "<!-- nothing here -->\n"
    "ftp://example.invalid/file\n"
    "</textarea>"
    "</body></html>"
)


class _Extractor:
    """Gemeinsame Assertions fuer beide Extraktions-Pfade."""

    def extract(self, html):
        raise NotImplementedError

    def test_reads_every_line_of_the_textarea(self):
        links = self.extract(TRURL_PAGE)
        self.assertEqual(links, [
            "https://rapidgator.net/file/aaaa1111",
            "https://ddownload.com/bbbb2222/film.mkv",
        ])

    def test_reads_hoster_that_is_not_in_the_pattern_list(self):
        """Ein unbekannter Hoster wird nicht weggefiltert."""
        html = ("<html><body><textarea class='trurl'>"
                "https://unknown-hoster.example/dl/xyz"
                "</textarea></body></html>")
        self.assertEqual(self.extract(html), ["https://unknown-hoster.example/dl/xyz"])

    def test_drops_blank_lines_and_non_http_entries(self):
        links = self.extract(TRURL_MESSY_PAGE)
        self.assertEqual(links, ["https://rapidgator.net/file/dddd4444"])

    def test_anchor_layout_still_works_as_fallback(self):
        """Ohne Textarea greift weiterhin der Anker-Pfad."""
        self.assertEqual(self.extract(ANCHOR_PAGE),
                         ["https://rapidgator.net/file/cccc3333"])

    def test_empty_page_yields_nothing(self):
        self.assertEqual(self.extract("<html><body></body></html>"), [])

    def test_duplicates_are_collapsed(self):
        html = ("<html><body><textarea class='trurl'>"
                "https://rapidgator.net/file/eeee5555\n"
                "https://rapidgator.net/file/eeee5555\n"
                "</textarea></body></html>")
        self.assertEqual(self.extract(html), ["https://rapidgator.net/file/eeee5555"])


class DispatcherTrurlTest(_Extractor, unittest.TestCase):
    def extract(self, html):
        dispatcher = DBCDispatcher(state_module=SimpleNamespace(values={}))
        return dispatcher._extract_keeplinks_download_links(_soup(html))


class WebUiTrurlTest(_Extractor, unittest.TestCase):
    def extract(self, html):
        return extract_download_links(_soup(html))


if __name__ == "__main__":
    unittest.main()