# -*- coding: utf-8 -*-
"""Vertrag zwischen ``webui/src/lib/api.ts`` und den Bottle-Routen.

Der React-Client kennt seine URLs als Zeichenketten (``'/categories'``,
`` `/packages/${id}/...` ``). Das Backend kennt sie als Bottle-Regeln
(``'/api/categories/<category_id>'``). Zwischen beiden gab es keinen
automatischen Zusammenhang: ein Tippfehler in einer der beiden Stellen fiel
erst zur Laufzeit auf, als 404 im Browser - bzw. gar nicht, weil der
SPA-Catch-all ``/<path:path>`` jede unbekannte URL mit der Startseite
beantwortet.

Dieser Test haelt die beiden Listen mechanisch zusammen. Er schickt keine
Requests - er liest nur die Routenliste der gebauten App und die
Aufrufstellen im Client und vergleicht Pfad und Methode.

Drei Dinge, die den Test ehrlich halten:

* Der SPA-Catch-all ``/<path:path>`` und die *arr-Schimme ``/api/<mirror>``
  werden **nicht** als Treffer gewertet. Sie wuerden jede denkbare URL
  "registriert" aussehen lassen und den Test still gruen machen.
* Der Parser muss eine Mindestzahl an Aufrufstellen finden. Findet er
  nichts (Syntaxänderung im Client), schlaegt der Test fehl, statt alles
  als leer zu akzeptieren.
* Client-Aufrufe ohne Gegenstuecke im Backend sind als benannte Liste
  festgeschrieben (``_BEKANNTE_LUECKEN``). Eine neue Luecke - und eine
  geschlossene alte - machen den Test rot.
"""

import difflib
import os
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import bottle

# --------------------------------------------------------------------------
# Pfade
# --------------------------------------------------------------------------

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_TS = os.path.join(_REPO_ROOT, "kuasarr", "webui", "src", "lib", "api.ts")
WEBUI_SRC = os.path.join(_REPO_ROOT, "kuasarr", "webui", "src")

#: Platzhalter fuer ein `${...}`-Segment. Enthaelt keine Zeichen, die in
#: einer echten Route vorkommen - sonst wuerde ein Platzhalter stillschweigend
#: gegen ein regulaeres Segment matchen.
PARAM = "__param__"

#: Anzeige-Form desselben Platzhalters, nur fuer Fehlermeldungen.
DISPLAY_PARAM = "{…}"

#: Routen, die zwar registriert sind, aber bewusst *nicht* als Beleg gelten,
#: dass ein Client-Pfad existiert. Begruendung je Route:
#:
#: - ``/<path:path>``: der SPA-Catch-all. Er matcht jeden Pfad und liefert
#:   fuer ``api/...`` ein 404 - im Browser sieht das also wie eine
#:   vorhandene Route aus, obwohl die API-Route fehlt. Ohne diese Ausnahme
#:   waere der Test ein reiner Gemuetlichkeitsnachweis.
#: - ``/api/<mirror>``: die Newznab-Schimme fuer Radarr/Sonarr. Sie
#:   matcht *jedes* einzelne Segment unter ``/api`` per GET. Ein Tippfehler
#:   wie ``/api/hostser`` liefe dann gegen sie statt gegen ein 404.
SHADOW_RULES = frozenset({
    "/<path:path>",
    "/api/<mirror>",
})

#: Client-Aufrufe, fuer die das Backend keine Route hat - heute keine.
#:
#: Aktuell ist die Liste leer: jeder Aufruf in ``api.ts`` hat eine
#: Entsprechung. Bis #96 standen hier sechs Funktionen, die das Backend
#: nie hatte (``/api/packages/<id>``, ``/api/search/status/<id>``,
#: ``/api/statistics/history``, ``/api/notifications/configs`` und
#: ``/api/notifications/configs/<id>``). Sie waren exportiert, wurden aber
#: von keiner Komponente aufgerufen - toter Client-Code.
#:
#: Die Liste existiert trotzdem, damit so ein Fall nicht wieder still
#: durchrutscht: taucht ein Aufruf ohne Route auf, wird dieser Test rot.
#: Aufnehmen darf man ihn nur, wenn die Funktion nachweislich nirgends
#: benutzt wird - das prueft ``test_the_known_gaps_are_really_unused``.
_BEKANNTE_LUECKEN = frozenset()


# --------------------------------------------------------------------------
# Harness: die echte App bauen, nur den Server-Start ersetzen
# --------------------------------------------------------------------------


class _FakeConfig:
    """Nur die geteilten ``get``/``save`` der echten Config."""

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
    """Die drei Zugriffe, die die Statistik-Provider beim Start tun.

    Der echte ``DataBase`` will eine offene SQLite-Datei. Fuer eine
    Routenliste reicht eine Attrappe ohne Zeilen: sie kann keine Zeile
    liefern, die einen Test in die Irre fuehren koennte.
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


def _build_app():
    """Baut die App aus ``kuasarr.api.get_api`` und liefert sie zurueck.

    Identisch zum Harness aus ``test_api_contract_core`` - nur ohne WSGI:
    hier zaehlt ausschliesslich, welche Regeln auf der App gelandet sind.
    """
    store = {
        "API": {"key": "master-key-abc"},
        "WebUI": {"api_token": "browser-token-xyz"},
        "JDownloader": {"user": "", "password": "", "device": ""},
    }
    app = bottle.Bottle()
    configdir = tempfile.TemporaryDirectory()

    state = {
        "configfile": os.path.join(configdir.name, "kuasarr.ini"),
        "dbfile": os.path.join(configdir.name, "kuasarr.db"),
        "database": _FakeDatabase,
        "port": 8080,
    }

    from unittest.mock import patch as _patch
    started = []
    for name in ("kuasarr.api.Config", "kuasarr.providers.auth.Config",
                 "kuasarr.providers.ui.html_templates.Config"):
        patcher = _patch(name, _make_config(store))
        patcher.start()
        started.append(patcher)

    try:
        with patch("kuasarr.providers.shared_state.get_db"), \
                patch("kuasarr.api.Bottle", return_value=app), \
                patch("kuasarr.api.Server"):
            from kuasarr.api import get_api
            get_api(state, _FakeLock())
    finally:
        for p in started:
            p.stop()

    app._kuasarr_configdir = configdir  # haelt den Tempdir am Leben
    return app


# --------------------------------------------------------------------------
# Client-Seite: api.ts parsen
# --------------------------------------------------------------------------

_FUNCTION_DECL = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(")
_METHOD_IN_ARGS = re.compile(r"\bmethod\s*:\s*['\"]([A-Za-z]+)['\"]")
_CALL_START = re.compile(r"\b(fetchApi|fetch)\b")


class ClientCall(object):
    """Eine Aufrufstelle im Client: Funktion, Methode, Pfad, Zeile."""

    def __init__(self, function, method, path, raw, line):
        self.function = function
        self.method = method
        self.path = path
        self.raw = raw
        self.line = line

    def key(self):
        """Vergleichsschluessel - fuer Fehlermeldungen lesbar gemacht."""
        return (self.function, self.method, self.display())

    def display(self):
        return self.path.replace(PARAM, DISPLAY_PARAM)

    def __repr__(self):
        return "%s() %s %s" % (self.function, self.method, self.display())


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _mask_fetch_api_body(source):
    """Blendet den Rumpf von ``fetchApi`` aus.

    ``fetch(`${API_BASE}${endpoint}`)`` ist der Durchreiche-Aufruf: seine
    URL ist bereits durch jeden einzelnen ``fetchApi(...)``-Aufruf abgedeckt.
    Zaehlte man ihn mit, entstuende ein Pfad ``/api/__param__``, der gegen
    alles matcht.
    """
    marker = source.find("async function fetchApi")
    if marker == -1:
        marker = source.find("function fetchApi")
    if marker == -1:
        return source
    start = source.find("{", marker)
    if start == -1:
        return source
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[:start] + " " * (index - start) + source[index:]
    return source


def _find_call_arguments(source, index):
    """Liefert den Argumenttext eines Aufrufs ab der Klammer hinter ``index``.

    Beruecksichtigt Strings, Template-Literale und verschachtelte
    Klammern/Object-Literale - sonst zerlegt ein ``JSON.stringify({...})``
    die Argumentliste in Unsinn.
    """
    open_paren = source.find("(", index)
    if open_paren == -1:
        return None

    stack = []
    quote = None
    i = open_paren
    while i < len(source):
        char = source[i]
        if quote:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                quote = None
            i += 1
            continue
        if char in "'\"`":
            quote = char
        elif char in "([{":
            stack.append(char)
        elif char in ")]}":
            if not stack:
                return None
            stack.pop()
            if not stack:
                return source[open_paren + 1:i]
        i += 1
    return None


def _split_arguments(argument_text):
    """Teilt eine Argumentliste an den Komma auf oberster Ebene."""
    arguments = []
    buffer = []
    stack = []
    quote = None
    i = 0
    while i < len(argument_text):
        char = argument_text[i]
        if quote:
            buffer.append(char)
            if char == "\\" and quote != "`":
                buffer.append(argument_text[i + 1])
                i += 2
                continue
            if char == quote:
                quote = None
            i += 1
            continue
        if char in "'\"`":
            quote = char
            buffer.append(char)
        elif char in "([{":
            stack.append(char)
            buffer.append(char)
        elif char in ")]}":
            stack.pop()
            buffer.append(char)
        elif char == "," and not stack:
            arguments.append("".join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)
        i += 1
    tail = "".join(buffer).strip()
    if tail:
        arguments.append(tail)
    return arguments


def _string_value(expression):
    """Wert eines String- oder Template-Literals, sonst ``None``."""
    expression = expression.strip()
    if len(expression) >= 2 and expression[0] == expression[-1] \
            and expression[0] in "'\"`":
        return expression[1:-1]
    return None


def _split_ternary(expression):
    """``a ? b : c`` -> ``[a, b, c]``, sonst ``None``.

    ``getPackages`` waehlt so den Pfad: mit und ohne Query-Parameter. Fuer den
    Vergleich zaehlen beide Zweige - der Query-String wird ohnehin weg.
    """
    stack = []
    quote = None
    question = None
    colon = None
    i = 0
    while i < len(expression):
        char = expression[i]
        if quote:
            if char == "\\" and quote != "`":
                i += 2
                continue
            if char == quote:
                quote = None
            i += 1
            continue
        if char in "'\"`":
            quote = char
        elif char in "([{":
            stack.append(char)
        elif char in ")]}":
            stack.pop()
        elif not stack:
            if char == "?" and question is None:
                question = i
            elif char == ":" and question is not None and colon is None:
                colon = i
        i += 1
    if question is None or colon is None:
        return None
    return [expression[:question], expression[question + 1:colon],
            expression[colon + 1:]]


def _normalise_path(raw_path):
    """Template-Text -> vergleichbarer Pfad mit Platzhaltern.

    ``/packages/${id}`` -> ``/packages/__param__``. Query-Stringe fallen
    weg: Bottle routet nach ``PATH_INFO``, nicht nach ``QUERY_STRING``.
    """
    text = re.sub(r"\$\{[^}]*\}", PARAM, raw_path)
    text = text.split("?", 1)[0]
    return text


def _api_base(source):
    """``const API_BASE = '/api'`` - der Prefix, den ``fetchApi`` davorhaengt.

    Aus der Datei gelesen statt fest verdrahtet: aendert sich der Prefix,
    aendert sich der Test mit - sonst pruefte er weiter gegen ``/api``,
    obwohl der Client woanders hingeht.
    """
    match = re.search(r"\bconst\s+API_BASE\s*=\s*['\"]([^'\"]*)['\"]", source)
    return match.group(1) if match else "/api"


def _parse_api_ts(source):
    """Alle ``fetch``/``fetchApi``-Aufrufstellen des Clients.

    ``fetchApi('/x')`` wird zu ``/api/x`` vollstaendig - der Prefix kommt
    erst in ``fetch`` dazu, und der Durchreiche-Aufruf ist ausgeblendet.
    Ein direktes ``fetch('/api/key')`` traegt den Prefix schon.

    :return: Liste von :class:`ClientCall`.
    """
    source = _mask_fetch_api_body(source)
    base = _api_base(source)
    constants = _local_constants(source)
    calls = []
    seen = set()

    for match in _CALL_START.finditer(source):
        open_paren = source.find("(", match.end())
        if open_paren == -1:
            continue
        # Zwischen Name und Klammer darf ein Generic stehen
        # (``fetchApi<Category[]>(...)``).
        between = source[match.end():open_paren]
        if between.strip() and not re.fullmatch(r"<[\s\S]*>", between):
            continue

        argument_text = _find_call_arguments(source, match.end())
        if argument_text is None:
            continue
        arguments = _split_arguments(argument_text)
        if not arguments:
            continue

        method_match = _METHOD_IN_ARGS.search(argument_text)
        method = (method_match.group(1).upper() if method_match else "GET")

        function = _enclosing_function(source, match.start())
        line = source.count("\n", 0, match.start()) + 1

        for expression in _resolve_endpoint(arguments[0], constants):
            if expression is None:
                continue
            # ``fetchApi`` haengt den Prefix davor, ein direktes ``fetch``
            # bringt die vollstaendige URL mit.
            raw_path = expression if match.group(1) == "fetch" \
                else base + expression
            path = _normalise_path(raw_path)
            call = ClientCall(function, method, path, arguments[0], line)
            if call.key() in seen:
                continue
            seen.add(call.key())
            calls.append(call)
    return calls


def _enclosing_function(source, index):
    """Name der Funktion, in der ``index`` liegt (oder ``'<modul>'``)."""
    name = None
    for match in _FUNCTION_DECL.finditer(source):
        if match.start() > index:
            break
        name = match.group(1)
    return name or "<modul>"


def _resolve_endpoint(expression, constants=None, depth=0):
    """Loest das erste Argument eines Client-Aufrufs auf.

    Akzeptiert Literale, Template-Literale, Bedingungen
    (``status ? A : B``) und Verweise auf lokale ``const``-Variablen.
    """
    if expression is None or depth > 5:
        return []
    text = expression.strip().rstrip(";")
    literal = _string_value(text)
    if literal is not None:
        return [_normalise_path(literal)]

    branches = _split_ternary(text)
    if branches:
        result = []
        result.extend(_resolve_endpoint(branches[1], constants, depth + 1))
        result.extend(_resolve_endpoint(branches[2], constants, depth + 1))
        return result

    if re.fullmatch(r"[A-Za-z_$][\w$]*", text):
        if constants is not None:
            value = constants.get(text)
            if value is not None:
                return _resolve_endpoint(value, constants, depth + 1)
    return []


def _local_constants(source):
    """``const NAME = ...;`` aus einer Ebene - flach, ohne Auswertung."""
    constants = {}
    for match in re.finditer(
            r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*([^;]+);", source):
        constants[match.group(1)] = match.group(2)
    return constants


# --------------------------------------------------------------------------
# Backend-Seite: Bottle-Regeln uebersetzen
# --------------------------------------------------------------------------

_WILDCARD = re.compile(r"<([^<>:]+)(?::(re:)?([^>]*))?>")


def rule_to_regex(rule):
    """Bottle-Regel -> Regex, die einen echten Pfad matcht.

    Unterstuetzt die drei Formen, die im Projekt vorkommen:

    * ``:name``                -> ein Segment ohne ``/``
    * ``<name>``               -> wie ``:name``
    * ``<name:path>``          -> darf ``/`` enthalten (``[^/]+`` wuerde eine
      Route wie ``/static/<filename:path>`` nie matchen)
    * ``<name:re:...>``        -> der eingebettete Ausdruck
    """
    pattern = ["^"]
    index = 0
    for match in _WILDCARD.finditer(rule):
        pattern.append(re.escape(rule[index:match.start()]))
        filter_expression = match.group(3)
        if match.group(2):  # re:...
            pattern.append("(?:%s)" % filter_expression)
        elif filter_expression == "path":
            pattern.append(".+")
        else:
            pattern.append("[^/]+")
        index = match.end()
    pattern.append(re.escape(rule[index:]))
    pattern.append("$")
    return re.compile("".join(pattern))


def registered_routes(app):
    """``[(method, rule)]`` aller registrierten Routen, Schatten ausgenommen."""
    routes = []
    for route in app.routes:
        if route.rule in SHADOW_RULES:
            continue
        routes.append((route.method.upper(), route.rule))
    return routes


def shadow_rules_present(app):
    """Die Ausnahmen aus ``SHADOW_RULES`` muessen wirklich existieren."""
    rules = {route.rule for route in app.routes}
    return SHADOW_RULES - rules


def matches(client_path, method, routes):
    """Trifft ``client_path`` mit ``method`` eine der Routen?"""
    for route_method, rule in routes:
        if route_method != method:
            continue
        if rule_to_regex(rule).match(client_path):
            return True
    return False


def _segment_score(client_segments, rule_segments):
    """Wie viele Segmenten von vorn stimmen ueberein?

    Ein Platzhalter im Client und ein Wildcard-Segment in der Bottle
    zaehlen als halbe Uebereinstimmung: sie widersprechen sich nicht, sagen
    aber wenig aus. Zwei verschiedene feste Segmente brechen sofort ab -
    dahinter zu vergleichen waere geraten.
    """
    score = 0
    for client_segment, rule_segment in zip(client_segments, rule_segments):
        wildcard = (client_segment == PARAM
                    or rule_segment.startswith(("<", ":")))
        if wildcard:
            score += 1
        elif client_segment == rule_segment:
            score += 2
        else:
            break
    return score


def nearest_routes(client_path, method, routes, limit=4):
    """Die wahrscheinlichsten Kandidaten fuer eine Fehlermeldung.

    ``/api/pakets/abc`` soll auf ``/api/packages`` zeigen und nicht auf die
    beiden Dutzend anderen Routen unter ``/api``. Deshalb wird nach den
    gemeinsamen Segmenten von vorn gerannt; ``difflib`` ist nur der
    AuffangNetz fuer den Fall, dass gar nichts passt.
    """
    client_segments = client_path.strip("/").split("/")
    scored = []
    for route_method, rule in routes:
        score = _segment_score(client_segments, rule.strip("/").split("/"))
        # Innerhalb einer Score-Stufe entscheidet die Aehnlichkeit der
        # Zeichenketten - sonst gewinnt alphabetisch die erste von zwanzig
        # Routen unter ``/api``.
        ratio = difflib.SequenceMatcher(None, client_path, rule).ratio()
        scored.append((score, ratio, route_method, rule))
    scored.sort(key=lambda item: (-item[0], item[2] != method, -item[1],
                                  item[3]))

    best = scored[0][0] if scored else 0
    candidates = [item for item in scored if item[0] == best and best > 0]
    if len(candidates) < limit:
        target = "%s %s" % (method, client_path)
        formatted = ["%s %s" % (m, r) for m, r in routes]
        for entry in difflib.get_close_matches(target, formatted, n=limit,
                                               cutoff=0.4):
            parts = tuple(entry.split(" ", 1))
            if parts not in [(c[2], c[3]) for c in candidates]:
                candidates.append((0, False, parts[0], parts[1]))

    return [(item[2], item[3]) for item in candidates[:limit]]


def describe_mismatch(call, routes):
    """Lesbare Fehlermeldung: was der Client will, was es gibt."""
    candidates = nearest_routes(call.path, call.method, routes)
    lines = [
        "Die WebUI ruft eine Route auf, die es im Backend nicht gibt:",
        "",
        "  Client : %s() -> %s %s" % (call.function, call.method,
                                      call.display()),
        "           %s:%d" % ("kuasarr/webui/src/lib/api.ts", call.line),
        "           Quelltext: fetchApi(%s)" % call.raw.strip(),
        "",
        "  Fehlt : %s %s" % (call.method, call.display()),
    ]
    if candidates:
        lines.append("")
        lines.append("  Aehnlichste registrierte Routen:")
        for route_method, rule in candidates:
            lines.append("    %-6s %s" % (route_method, rule))
    else:
        lines.append("")
        lines.append("  Es gibt keine aehnliche registrierte Route.")
    lines += [
        "",
        "  Entweder die Route im Backend ergaenzen oder den Aufruf im",
        "  Client korrigieren. Beides ohne diesen Test zu finden ist",
        "  Sichtarbeit: der SPA-Catch-all '/<path:path>' beantwortet",
        "  jede unbekannte URL und verdeckt den 404 im Browser.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Welche Client-Funktionen benutzt die WebUI ueberhaupt?
# --------------------------------------------------------------------------


def _client_function_is_used(name, tree=WEBUI_SRC):
    """Wird ``name`` ausserhalb von ``api.ts`` irgendwo aufgerufen?

    Nur so trennt toter Client-Code von einer echten Luecke: eine
    unbenutzte Funktion kann keinen Aufrufer in die Irre fuehren, eine
    benutzte schon. Die Gegenprobe bestaetigt das - beide Faelle machen
    den Test rot, nur mit unterschiedlicher Begruendung.
    """
    pattern = re.compile(r"\b%s\s*\(" % re.escape(name))
    for directory, _dirs, files in os.walk(tree):
        for filename in files:
            if not filename.endswith((".ts", ".tsx")):
                continue
            path = os.path.join(directory, filename)
            if os.path.abspath(path) == os.path.abspath(API_TS):
                continue
            if pattern.search(_read(path)):
                return True
    return False


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


class TestWebUiApiClientContract(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.source = _read(API_TS)
        cls.app = _build_app()
        cls.routes = registered_routes(cls.app)
        cls.calls = _parse_api_ts(cls.source)

    # -- Der Parser selbst ------------------------------------------------

    def test_the_parser_finds_the_client_calls(self):
        """Kein still gruener Test, weil der Parser nichts findet.

        Aendert sich die Syntax in ``api.ts`` (etwa ``fetch(...)`` statt
        ``fetchApi(...)``), muss das hier auffallen, statt dass alle
        Vergleiche ueber einer leeren Liste "gruen" werden.
        """
        found = {call.key() for call in self.calls}
        self.assertGreaterEqual(
            len(self.calls), 30,
            "Der Parser hat nur %d Aufrufstellen gefunden - er liest "
            "api.ts vermutlich nicht mehr vollstaendig." % len(self.calls))

        # Stichproben aus jedem Bereich des Clients, die mit Namen bekannt
        # sind: faellt eine Zone aus, faellt es hier auf.
        expected = {
            ("getCategories", "GET", "/api/categories"),
            ("createCategory", "POST", "/api/categories"),
            ("deleteCategory", "DELETE",
             "/api/categories/" + DISPLAY_PARAM),
            ("getPackages", "GET", "/api/packages"),
            ("pausePackages", "POST", "/api/packages/pause"),
            ("search", "POST", "/api/search"),
            ("getStatistics", "GET", "/api/statistics"),
            ("saveNotificationSettings", "POST", "/api/notifications"),
            ("getAdvancedSettings", "GET", "/api/settings/advanced-config"),
        }
        missing = expected - found
        self.assertFalse(missing, "Vom Parser nicht gefunden: %s" % sorted(missing))

    def test_a_query_parameter_never_becomes_part_of_the_path(self):
        """``/packages?status=...`` wird gegen ``/api/packages`` geprueft.

        Sonst waere jeder GET mit Query-String ein Fehlalarm.
        """
        paths = {call.path for call in self.calls}
        self.assertFalse([p for p in paths if "?" in p],
                         "Query-Strings duerfen nicht im Pfad landen: %s"
                         % sorted(p for p in paths if "?" in p))
        # ``getPackages`` baut den Pfad erst zur Laufzeit zusammen:
        # ``status ? '/packages?status=...' : '/packages'``. Beide Zweige
        # muessen auf denselben registrierten Pfad zeigen.
        self.assertIn("/api/packages", paths)

    # -- Der eigentliche Vergleich ----------------------------------------

    def test_every_used_client_call_hits_a_registered_route(self):
        """Der Kern: kein Aufruf der SPA darf ins Leere laufen.

        Bewusst werden nur die Aufrufe geprueft, die eine Komponente auch
        wirklich benutzt - siehe ``_BEKANNTE_LUECKEN`` fuer den Rest.
        """
        broken = []
        for call in self.calls:
            if matches(call.path, call.method, self.routes):
                continue
            if not _client_function_is_used(call.function):
                continue
            broken.append(call)

        self.assertEqual(
            broken, [],
            "\n\n".join(describe_mismatch(call, self.routes) for call in broken))

    def test_the_known_gaps_are_exactly_the_known_gaps(self):
        """Toter Client-Code ist eine benannte Liste, kein Loch im Test.

        Wird eine Client-Funktion neu aufgerufen, ohne dass das Backend
        die Route hat, ist sie nicht mehr "ungenutzt" und wird vom Test
        oben gefangen. Taucht hier etwas Neues auf, ist es mindestens einen
        Kommentar wert - oder ein Fehler.
        """
        gaps = {call.key() for call in self.calls
                if not matches(call.path, call.method, self.routes)}
        self.assertEqual(
            gaps, set(_BEKANNTE_LUECKEN),
            "Die Liste der Client-Aufrufe ohne Backend-Route hat sich "
            "geaendert.\n\n  Neu bzw. weg: %s\n\n"
            "Sind es tote Funktionen, gehoeren sie nach "
            "_BEKANNTE_LUECKEN; hat das Backend sie nachgezogen, "
            "gehoeren sie von dort weg."
            % sorted(gaps ^ set(_BEKANNTE_LUECKEN)))

    def test_the_known_gaps_are_really_unused(self):
        """Die Ausnahme gilt nur fuer Code, den niemand aufruft.

        Sonst waere sie eine hintere Hintertuer: sobald eine Komponente
        ``getStatisticsHistory()`` benutzt, muss das Backend die Route
        haben - und der Test muss das melden.
        """
        for function, method, path in sorted(_BEKANNTE_LUECKEN):
            with self.subTest(function=function):
                self.assertFalse(
                    _client_function_is_used(function),
                    "%s() wird inzwischen von der WebUI benutzt. Damit ist "
                    "%s %s eine echte Luecke und keine tolerierte - "
                    "entweder das Backend ergaenzen oder die Funktion aus "
                    "api.ts nehmen." % (function, method, path))

    # -- Selbstpruefungen des Vergleichs ----------------------------------

    def test_the_spa_catch_all_cannot_pass_for_an_api_route(self):
        """Der haeufigste Grund fuer einen blinden Test.

        ``/<path:path>`` matcht alles. Ohne Ausnahme wuerde jeder
        Tippfehler als "registriert" durchgehen.
        """
        self.assertEqual(shadow_rules_present(self.app), set(),
                         "SHADOW_RULES nennt Routen, die es nicht mehr "
                         "gibt - die Liste aktualisieren, sonst schuetzt "
                         "sie nichts mehr.")
        self.assertFalse(
            matches("/api/gibt-es-nicht", "GET", self.routes),
            "Eine nicht registrierte API-Route darf nicht als vorhanden "
            " gelten - dann waere der Test blind.")
        self.assertFalse(
            matches("/api/typo-in-hosters", "GET", self.routes),
            "Auch die *arr-Schimme '/api/<mirror>' darf keinen Tippfehler "
            "verdecken.")

    def test_a_method_mismatch_is_not_accepted(self):
        """Pfad passt, Methode nicht -> trotzdem ein Fehler.

        ``POST /api/notifications/test`` gibt es, ein ``GET`` darauf nicht.
        Ohne Methodenpruefung wuerde ein umgestellter Client-Aufruf
        durchrutschen und der Nutzer bekaeme eine HTML-Seite.
        """
        self.assertTrue(
            matches("/api/notifications/test", "POST", self.routes))
        self.assertFalse(
            matches("/api/notifications/test", "GET", self.routes))

    def test_bottle_wildcards_are_translated_correctly(self):
        """Die drei Fluege der Bottle-Syntax landen im Regex.

        Ein ``<name:path>`` darf ``/`` enthalten - mit ``[^/]+`` wuerde
        ``/static/<filename:path>`` prinzipiell nie matchen.
        """
        self.assertTrue(
            matches("/static/logo.png", "GET", self.routes))
        self.assertTrue(
            matches("/api/packages/ein/hash-mit/slash", "GET",
                    [("GET", "/api/packages/<id:path>")]))
        self.assertFalse(
            matches("/api/packages", "GET", [("GET", "/api/packages/<id>")]))

    def test_the_failure_message_names_the_call_and_a_candidate(self):
        """Ohne Kontext ist ein roter Test wertlos.

        Geprueft wird auch die Kandidatensuche: bei einem Tippfehler wie
        ``/api/pakets/...`` muss die naechstliegende *echte* Route
        (``/api/packages``) genannt werden, nicht irgendeine der
        Dutzend anderen unter ``/api``.
        """
        bogus = ClientCall("getPackages", "GET", "/api/pakets/" + PARAM,
                           "`/pakets/${id}`", 144)
        message = describe_mismatch(bogus, self.routes)
        self.assertIn("getPackages", message)
        self.assertIn("/api/pakets/" + DISPLAY_PARAM, message)
        self.assertIn("api.ts:144", message)
        self.assertIn("/api/packages", message)  # Kandidat genannt
        self.assertIn("Quelltext", message)


if __name__ == "__main__":
    unittest.main()