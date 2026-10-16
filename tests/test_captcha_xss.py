# -*- coding: utf-8 -*-
"""Fremdbestimmter Inhalt darf auf der CAPTCHA-Seite kein Markup einschleusen.

Der Release-Titel, der Mirror-Name und die Container-URL stammen von der
gescrapten Seite. Wer sie kontrolliert - und bei DDL-Hostern ist das der
Hoster, nicht der Betreiber -, kontrolliert damit auch diese Seite. Vor dem
Fix landeten sie roh in Attributen und Textknoten:

    <option value="{link[0]}">{link[1]}</option>
    <input type="hidden" name="title" value="{title}" />
    <div id="mirrors-select">Mirror: <b>{link[1]}</b></div>

Ein Titel wie ``x" onerror="alert(1)`` genügte, um das value-Attribut zu
verlassen und ein Attribut zu eröffnen, das sofort ausgeführt wird.
"""

import re
import unittest
from unittest.mock import MagicMock, patch

from kuasarr.api.captcha.ui_components import render_bypass_section
from kuasarr.providers.ui.html_templates import render_button

PAYLOAD = '"><img src=x onerror=alert(1)>'
SCRIPT_PAYLOAD = '</script><img src=x onerror=alert(1)>'


class TestRenderButtonEscapes(unittest.TestCase):
    def test_attribute_value_cannot_close_the_attribute(self):
        html = render_button("Go", "primary", {"onclick": PAYLOAD})
        self.assertNotIn('onerror=alert(1)>', html)
        self.assertIn("&quot;", html)

    def test_text_is_escaped(self):
        html = render_button("<b>not bold</b>", "primary")
        self.assertNotIn("<b>not bold</b>", html)
        self.assertIn("&lt;b&gt;not bold&lt;/b&gt;", html)

    def test_ordinary_button_still_works(self):
        """Escaping darf onclick nicht unbrauchbar machen.

        `&#x27;` ist innerhalb eines doppelt gequoteten Attributs genau das
        gleiche wie `'` - der HTML-Parser dekodiert es, bevor JS die Zeile
        sieht. Deshalb wird an dieser Stelle auch `'` escaped und nicht nur
        das Anfuehrungszeichen, das das Attribut wirklich schliessen koennte.
        """
        html = render_button("Zurück", "secondary", {"onclick": "location.href='/'"})
        self.assertIn("btn-secondary", html)
        self.assertIn("Zurück", html)
        self.assertIn("location.href=&#x27;/&#x27;", html)


class TestBypassSectionEscapes(unittest.TestCase):
    def _render(self, **kwargs):
        params = dict(
            url="https://filecrypt.cc/Container/ABC.html",
            package_id="pkg-1",
            title=PAYLOAD,
            password=PAYLOAD,
        )
        params.update(kwargs)
        with patch("kuasarr.api.captcha.ui_components.request") as request:
            request.urlparts.scheme = "http"
            request.urlparts.netloc = "kuasarr:9999"
            return render_bypass_section(**params)

    def test_title_cannot_break_out_of_its_value_attribute(self):
        """Der entscheidende Punkt ist das fehlende rohe ``<``.

        ``onerror=alert(1)`` als Textfolge bleibt im escaped Wert durchaus
        stehen - entscheidend ist, dass es nirgends als Attribut einer neuen
        Marke gelesen werden kann, weil das ``<`` davor zu ``&lt;`` wurde.
        """
        html = self._render()
        self.assertNotIn("<img src=x", html)
        self.assertNotIn('value=""><img', html)

    def test_password_cannot_break_out_of_its_value_attribute(self):
        html = self._render()
        self.assertNotIn('name="password" value=""', html)
        self.assertIn('name="password" value="&quot;&gt;&lt;img', html)

    def test_title_value_is_escaped_verbatim(self):
        html = self._render()
        self.assertIn('name="title" value="&quot;&gt;&lt;img src=x', html)

    def test_url_cannot_rewrite_the_onclick_handler(self):
        """Der onclick-Wert lebt nach dem HTML-Decoding im JavaScript-Kontext.

        `render_button` escaped das Attribut - das genuegt nicht. Der Browser
        dekodiert `&#x27;` zurueck zu `'`, *bevor* JS die Zeile parst. Ein
        einfaches Anfuehrungszeichen in der Container-URL beendet den String
        also und alles danach ist ausfuehrbarer Code. Der Test liest deshalb
        das Attribut zurueck und dekodiert es so, wie es ein Browser tut.
        """
        html = self._render(url="https://fc/C.html'); alert(document.domain); //")
        handler = _decode_attribute(html, "onclick")
        self.assertEqual(_js_string_tail(handler), "', '_self')")

    def test_url_cannot_escape_through_ampersands(self):
        """Der Quick-Transfer-Anhang benutzt `&` als Trenner.

        Ohne Escaping koennte ein `&quot;` aus der Attribut-Dekodierung wieder
        zu einem Anfuehrungszeichen werden und damit den Wert aufspalten.
        """
        html = self._render(url="https://fc/C.html?a=1&b='")
        handler = _decode_attribute(html, "onclick")
        self.assertEqual(_js_string_tail(handler), "', '_self')")

    def test_missing_password_renders_instead_of_raising(self):
        """Ein Container ohne Passwort ist der Normalfall, kein Sonderfall.

        `payload.get("password")` liefert da None, und `quote(None` wirft
        TypeError - die CAPTCHA-Seite wurde damit zur 500, und zwar bei genau
        den Links, die man entschluesseln wollte.
        """
        html = self._render(password=None)
        self.assertIn("pkg_pass=&", html)


def _decode_attribute(document, attribute):
    """Liest ein Attribut zurueck und dekodiert es, wie ein Browser es tut."""
    import html as html_module

    raw = re.search(attribute + r'="([^"]*)"', document).group(1)
    return html_module.unescape(raw)


def _js_string_tail(handler):
    """Endposition des ersten JS-Strings plus dem, was danach kommt.

    Ein ausfuehrbares ``'); alert(1)`` aendert den Rest hinter dem String -
    genau das ist der Befund, den dieser Helfer sichtbar macht.
    """
    start = handler.index("'", handler.index("window.open("))
    index = start + 1
    while index < len(handler):
        if handler[index] == "\\":
            index += 2
            continue
        if handler[index] == "'":
            return handler[index:]
        index += 1
    return "!! String laeuft bis zum Ende der Zeile"


class _FakeApp:
    def __init__(self):
        self.routes = {}

    def get(self, path):
        def decorator(fn):
            self.routes[path] = fn
            return fn
        return decorator

    post = get


class TestCutcaptchaRouteEscapes(unittest.TestCase):
    """The real route, not a re-implementation of the escaping."""

    def _render(self, mirror_name, title=PAYLOAD, links=None, mirror=None):
        from kuasarr.api.captcha import provider_routes

        app = _FakeApp()
        with patch.object(provider_routes, "decode_payload", return_value={
            "package_id": "pkg-1",
            "title": title,
            "password": "",
            # `mirror` ist ein eigener Payload-Schluessel und geht in den
            # JS-Request-Body - nicht der Anzeigename aus `links`.
            "mirror": mirror if mirror is not None else mirror_name,
            "links": links if links is not None
            else [["https://filecrypt.cc/Container/ABC.html", mirror_name]],
        }), \
             patch.object(provider_routes, "check_package_exists"), \
             patch.object(provider_routes, "captcha_values",
                          return_value={"api_key": "k'"}):
            provider_routes.setup_provider_routes(app)
            # The route has to run inside the patch context: outside it the
            # real decode_payload runs, needs a request and hands back None.
            return app.routes["/captcha/cutcaptcha"]()

    def test_mirror_name_cannot_close_the_option(self):
        html = self._render(PAYLOAD)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img src=x", html)

    def test_package_title_cannot_close_its_element(self):
        html = self._render("rapidgator")
        self.assertNotIn("<img src=x", html)

    def test_api_key_cannot_break_out_of_the_js_string(self):
        html = self._render("rapidgator")
        self.assertNotIn("var api_key = \"k'\";", html)
        self.assertIn("var api_key = \"k\\'\";", html)

    def test_title_cannot_close_the_script_element(self):
        """``</script>`` beendet den Script-Block, auch ohne ein einziges Anfuehrungszeichen.

        Der HTML-Parser liest den Inhalt eines ``<script>`` als Rohtext, bis er
        auf ``</script>`` stoesst. Escaping der Anfuehrungszeichen allein
        genuegt darum nicht - der oeffnende Winkel des Schluss-Tags muss auch
        verschwinden.
        """
        html = self._render("rapidgator", title=SCRIPT_PAYLOAD)
        self.assertNotIn(SCRIPT_PAYLOAD, html)
        # Was danach noch als Text uebrig ist, steht in einem JS-String
        # innerhalb eines <script>-Elements und kann dort nichts eroeffnen -
        # entscheidend ist, dass kein oehnender Winkel das Element verlassen kann.
        self.assertIn("title: '\\u003c/script>", html)

    def test_password_cannot_close_the_js_string_it_is_written_into(self):
        """Passwort und Mirror-Name gingen unveraendert in JS-Strings.

        Beide kommen aus dem Payload und damit von der gescrapten Seite. Der
        Mirror-Name ist der Hoster - ein einzelnes Anfuehrungszeichen darin hat
        den restlichen Request-body als JavaScript ausgefuehrt.
        """
        html = self._render("rapidgator'); alert(1); //")
        self.assertNotIn("mirror: 'rapidgator'); alert(1); //',", html)
        self.assertIn("mirror: 'rapidgator\\'); alert(1); //',", html)

    def test_link_hidden_input_cannot_be_closed(self):
        """Das hidden input trug die Container-URL unveraendert.

        Es ist derselbe Wert wie im Mirror-<option>, aber an einer Stelle, die
        der erste Fix nicht abgedeckt hatte: ein Anfuehrungszeichen in der URL
        schliesst das value-Attribut und eroeffnet ein ausfuehrbares.
        """
        html = self._render("rapidgator", links=[[PAYLOAD, "rapidgator"]])
        self.assertNotIn('value=""><img', html)
        self.assertIn('id="link-hidden" value="&quot;&gt;&lt;img', html)


class TestCircleRouteRenders(unittest.TestCase):
    """Der Circle-Pfad war durch meine eigene Aenderung lahmgelegt."""

    def _render(self, **overrides):
        from kuasarr.api.captcha import provider_routes

        payload = {
            "package_id": "pkg-1",
            "session": "s1",
            "title": "Titel",
            "password": "",
            "original_url": "",
            "links": [["https://filecrypt.cc/C.html", "rapidgator"]],
        }
        payload.update(overrides)

        app = _FakeApp()
        with patch.object(provider_routes, "decode_payload", return_value=payload), \
             patch.object(provider_routes, "check_package_exists"):
            provider_routes.setup_provider_routes(app)
            return app.routes["/captcha/circle"]()

    def test_it_renders(self):
        """Regression: die Route benutzte `safe_title`, ohne es zu definieren.

        `title` wird hier mit Default gelesen, nicht mit `.get("title")` -
        deshalb traf der Ersetzungsschritt die Verwendung, aber nicht die
        Definition. Ergebnis war auf jeder Circle-Captcha ein NameError.
        """
        self.assertIn("Titel", self._render())

    def test_the_form_query_is_encoded(self):
        """url und session_id standen roh in action- und src-Attribut.

        Geprueft wird nur das action-Attribut, nicht das ganze Dokument: die
        bypass-Sektion enthaelt die URL ebenfalls, dort aber zwingend als
        Teil eines JS-Strings - `onerror=` steht da harmlos als Text.
        """
        html = self._render(links=[["https://fc/C.html\" onerror=alert(1)", "rapidgator"]])
        action = re.search(r'<form action="([^"]*)"', html).group(1)
        self.assertNotIn("onerror=", action)
        # Innerhalb des url-Werts darf kein Anfuehrungszeichen mehr stehen -
        # das ist die Eigenschaft, auf die es hier ankommt, unabhaengig davon,
        # welche Zeichen quote() sonst noch kodiert.
        self.assertNotIn('"', action.split("?url=")[1])
        self.assertIn("session_id=s1", action)


if __name__ == "__main__":
    unittest.main()