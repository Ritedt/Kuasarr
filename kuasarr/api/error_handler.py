# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork from https://github.com/rix1337/Quasarr)

"""Einheitliche JSON-Fehlerantworten fuer die WebUI.

Ohne diesen Handler liefert Bottle fuer jeden ``abort()`` eine HTML-Fehlerseite.
``fetchApi`` in der React-WebUI parst die Antwort aber als JSON, scheitert daran
und zeigt dem Nutzer daraufhin immer ``Unknown error`` - egal ob der API-Key
fehlte, die Route nicht existiert oder der Server abgestuerzt ist.

Die WebUI erwartet ausschliesslich diese Form::

    {"error": {"code": "not_found", "message": "..."}}

Deshalb normalisiert dieser Handler jede Fehlermeldung darauf, unabhaengig
davon, ob sie aus einem ``abort()``, einer unbehandelten Exception oder einem
Handler mit flachem ``{"error": "text"}``-Payload stammt.
"""

import html
import json

from bottle import HTTP_CODES, HTTPResponse, request, response


def wants_json() -> bool:
    """Handelt es sich bei diesem Request um einen API-Aufruf der WebUI?"""
    path = request.path or ""
    return (
        path == "/api"
        or path.startswith("/api/")
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )


def error_response(status: int, message: str, code: str = None) -> dict:
    """Baut die Fehlerhuelle, die die WebUI erwartet."""
    return {"error": {"code": code or _code_for_status(status), "message": message}}


def json_error(status: int, message: str, code: str = None):
    """Fehlerhuelle als fertiger Response-Body, inklusive Statuscode.

    fuer Stellen, die bewusst ``return json.dumps(...)`` statt ``abort()``
    schreiben - etwa weil sie noch auf ``success``-Felder fuer aeltere
    Aufrufer pflegen. Der Statuscode wird hier gesetzt, weil er sonst
    stillschweigend 200 bleibt: ``fetchApi`` wirft nur bei
    ``!response.ok``, ein 200 mit ``success: false`` sieht der Client
    dagegen als Erfolg an.
    """
    response.status = status
    response.content_type = "application/json; charset=UTF-8"
    return json.dumps(error_response(status, message, code))


def _code_for_status(status: int) -> str:
    """Stabile, maschinenlesbare Codes statt eines Magic-Numbers-Strings."""
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        429: "too_many_requests",
        502: "bad_gateway",
    }.get(status, "error" if status < 500 else "internal_error")


# Bottle 0.13.4 definiert `def abort(code=500, text='Unknown Error.')` (bottle.py:2811).
# Ein `abort(404)` ohne Text landet also mit genau diesem Baustein als `HTTPError.body`
# an - nicht mit einer leeren Body, wie der aeltere Bottle-Standard behauptet.
_BOTTLE_PLACEHOLDER = "Unknown Error."


def _message_for_status(status: int, fallback: str) -> str:
    """Extrahiert eine lesbare Meldung aus dem, was Bottle mitbringt.

    Bottle haengt ``abort(403, "Invalid API Key")`` als ``body`` an. Ruft
    jemand dagegen ``abort(403)`` ohne Text, steht dort Bottles englischer
    Platzhalter - der dem Nutzer nichts sagt und zudem mit echten Meldungen
    kollidieren koennte. In dem Fall wird auf eine eigene Meldung
    zurueckgefallen.
    """
    body = (fallback or "").strip()
    if body and body != _BOTTLE_PLACEHOLDER:
        return body
    return _default_message(status)


def _default_message(status: int) -> str:
    return {
        400: "Invalid request",
        401: "Missing API key",
        403: "Access denied",
        404: "Not found",
        405: "Method not allowed",
        429: "Too many requests",
        500: "Internal server error",
    }.get(status, "Request failed")


def setup_error_handlers(app) -> None:
    """Registriert die JSON-Fehlerhandler fuer alle API-Pfade.

    Nur Statuscodes, kein ``@app.error(HTTPResponse)``: Bottle castet das
    Argument per ``int(code)`` und wuerde an der Klasse scheitern. Ein
    Handler, der ein fertiges ``HTTPResponse`` zurueckgibt, braucht es
    auch nicht - der Router uebernimmt das Objekt direkt, ohne den
    Fehlerpfad zu durchlaufen.
    """

    @app.error(400)
    @app.error(401)
    @app.error(403)
    @app.error(404)
    @app.error(405)
    @app.error(409)
    @app.error(429)
    @app.error(500)
    @app.error(502)
    def handle_error(error):
        status = error.status_code
        message = _message_for_status(status, _error_body(error))

        if not wants_json():
            return _html_error(status, message)

        response.content_type = "application/json; charset=UTF-8"
        return json.dumps(error_response(status, message))


def _html_error(status: int, message: str) -> HTTPResponse:
    """Die Fehlerseite fuer die Legacy-Routen ausserhalb von ``/api``.

    Bewusst als fertiges ``HTTPResponse`` und nicht als ``return error``:
    Bottle akzeptiert in einem Fehlerhandler kein ``HTTPError``-Objekt als
    Antwort und wertet das selbst als neuen Fehler - aus jedem 403 wuerde
    ein 500 mit ``Critical error while processing request``. Die Meldung
    geht dabei auch verloren, also wird die kleine Seite hier gebaut. Der
    Text wird escaped, weil er in anderen Faellen Nutzereingaben enthaelt
    (``abort(400, f"Invalid email '{email}'")``).
    """
    title = f"{status} {_reason(status)}"
    body = (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title></head>"
        f"<body><h1>{html.escape(title)}</h1><p>{html.escape(message)}</p>"
        "</body></html>"
    )
    return HTTPResponse(body, status=status,
                        content_type="text/html; charset=UTF-8")


def _reason(status: int) -> str:
    """Der Statustext aus Bottles Tabelle, damit hier nichts erfunden wird."""
    return HTTP_CODES.get(status, "Error")


def _error_body(error) -> str:
    """Liest den Text aus einem ``HTTPError``, ohne die Bottle-Standardseite zu uebernehmen."""
    body = getattr(error, "body", "")
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8", "replace")
    return body or ""