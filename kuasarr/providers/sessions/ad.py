# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

from __future__ import annotations

import base64
import json
import pickle
from typing import Optional
from urllib.parse import urlencode

import requests

from kuasarr.providers.log import debug, info

hostname = "ad"


def _auth_config(shared_state) -> tuple[Optional[str], Optional[str]]:
    cfg = shared_state.values["config"](hostname.upper())
    if not cfg:
        return None, None
    user = cfg.get("user") or cfg.get("email")
    password = cfg.get("password")
    return user, password


def _store_session(shared_state, session: requests.Session) -> None:
    blob = pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL)
    token = base64.b64encode(blob).decode("utf-8")
    shared_state.values["database"]("sessions").update_store(hostname, token)


def _load_session(token: str) -> Optional[requests.Session]:
    try:
        blob = base64.b64decode(token.encode("utf-8"))
        session = pickle.loads(blob)
        if isinstance(session, requests.Session):
            return session
    except Exception:
        pass
    return None


def _load_session_cookies_for_flaresolverr(session: Optional[requests.Session]):
    if not session:
        return []
    cookie_list = []
    for ck in session.cookies:
        cookie_list.append({
            "name": ck.name,
            "value": ck.value,
            "domain": ck.domain,
            "path": ck.path or "/",
        })
    return cookie_list


def _apply_solution_to_session(shared_state, session: requests.Session, solution: dict) -> None:
    user_agent = solution.get("userAgent")
    if user_agent:
        session.headers.update({"User-Agent": user_agent})

    cookies = solution.get("cookies", [])
    if cookies:
        session.cookies.clear()
        for ck in cookies:
            session.cookies.set(
                ck.get("name"),
                ck.get("value"),
                domain=ck.get("domain"),
                path=ck.get("path", "/"),
            )

    _store_session(shared_state, session)


def flaresolverr_request(shared_state, session: Optional[requests.Session], method: str, url: str,
                          data: Optional[dict] = None, timeout: int = 60) -> Optional[dict]:
    """Make request via FlareSolverr for Cloudflare bypass. Session is optional."""
    config_cls = shared_state.values.get("config")
    if not config_cls:
        info(f"{hostname}: Config-Handler nicht verfügbar")
        return None

    fs_config = config_cls("FlareSolverr")
    flaresolverr_url = fs_config.get("url")
    if not flaresolverr_url:
        info(f"{hostname}: FlareSolverr URL nicht konfiguriert")
        return None

    method = method.upper()
    cmd = "request.get" if method == "GET" else "request.post"

    payload = {
        "cmd": cmd,
        "url": url,
        "maxTimeout": timeout * 1000,
        "cookies": _load_session_cookies_for_flaresolverr(session) if session else [],
    }

    # Use session user agent if available, otherwise use shared state user agent
    if session:
        user_agent = session.headers.get("User-Agent")
    else:
        user_agent = shared_state.values.get("user_agent")
    
    if user_agent:
        payload["userAgent"] = user_agent

    if method == "POST" and data:
        payload["postData"] = urlencode(data)

    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(
            flaresolverr_url,
            headers=headers,
            data=json.dumps(payload),
            timeout=timeout + 10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        info(f"{hostname}: FlareSolverr Anfrage fehlgeschlagen ({exc})")
        return None

    try:
        fs_json = response.json()
    except ValueError:
        info(f"{hostname}: Ungültige Antwort von FlareSolverr")
        return None

    if fs_json.get("status") != "ok" or "solution" not in fs_json:
        info(f"{hostname}: FlareSolverr lieferte keine Lösung: {fs_json.get('message', '<unknown>')}")
        return None

    solution = fs_json.get("solution", {})
    
    # Only apply solution to session if session exists
    if session:
        _apply_solution_to_session(shared_state, session, solution)

    return {
        "status": solution.get("status"),
        "text": solution.get("response", ""),
        "headers": solution.get("headers", {}),
        "url": solution.get("url"),
    }


def _validate_session(shared_state, session: requests.Session) -> bool:
    host = shared_state.values["config"]("Hostnames").get(hostname)
    if not host:
        return False

    response = flaresolverr_request(shared_state, session, "GET", f"https://{host}/", timeout=60)
    if not response:
        return False

    content = (response.get("text") or "").lower()
    if "class=\"loglink\"" in content:
        return False
    if "logout" in content or "profile" in content:
        return True
    return False


def create_and_persist_session(shared_state) -> Optional[requests.Session]:
    host = shared_state.values["config"]("Hostnames").get(hostname)
    if not host:
        info(f"{hostname}: kein Hostname konfiguriert")
        return None

    user, password = _auth_config(shared_state)
    if not user or not password:
        info(f"{hostname}: fehlende Zugangsdaten")
        return None

    session = requests.Session()
    session.headers.update({"User-Agent": shared_state.values["user_agent"]})

    prime = flaresolverr_request(shared_state, session, "GET", f"https://{host}/", timeout=60)
    if not prime:
        info(f"{hostname}: Konnte Startseite nicht laden â€“ FlareSolverr erreichbar?")
        return None

    payload = {
        "login_name": user,
        "login_password": password,
        "login": "submit",
    }

    login_response = flaresolverr_request(
        shared_state,
        session,
        "POST",
        f"https://{host}/index.php?do=login",
        data=payload,
        timeout=60,
    )
    if not login_response:
        info(f"{hostname}: Login fehlgeschlagen â€“ FlareSolverr Antwort ungültig")
        return None

    if not _validate_session(shared_state, session):
        info(f"{hostname}: Login nicht erfolgreich â€“ bitte Zugangsdaten prüfen")
        return None

    _store_session(shared_state, session)
    info(f"{hostname}: neue Session erstellt und gespeichert")
    return session


def retrieve_and_validate_session(shared_state) -> Optional[requests.Session]:
    db = shared_state.values["database"]("sessions")
    token = db.retrieve(hostname)
    if token:
        session = _load_session(token)
        if session and _validate_session(shared_state, session):
            return session
        debug(f"{hostname}: gespeicherte Session ungültig â€“ erstelle neu")

    return create_and_persist_session(shared_state)


def invalidate_session(shared_state) -> None:
    shared_state.values["database"]("sessions").delete(hostname)
    debug(f"{hostname}: Session verworfen")


__all__ = [
    "create_and_persist_session",
    "retrieve_and_validate_session",
    "invalidate_session",
    "flaresolverr_request",
]




