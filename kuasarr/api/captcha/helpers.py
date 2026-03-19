# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337/Quasarr)

"""Helper functions for CAPTCHA routes."""

import json
from base64 import urlsafe_b64decode
from urllib.parse import unquote

from bottle import request, HTTPResponse

import kuasarr.providers.ui.html_images as images
from kuasarr.providers import shared_state
from kuasarr.providers.ui.html_templates import render_button, render_centered_html


def js_single_quoted_string_safe(text):
    """Escape text for use in single-quoted JavaScript strings."""
    return text.replace('\\', '\\\\').replace("'", "\\'")


def check_package_exists(package_id):
    """Check if package exists, raise 404 if not."""
    if not shared_state.get_db("protected").retrieve(package_id):
        raise HTTPResponse(
            status=404,
            body=render_centered_html(f'''
            <h1><img src="{images.logo}" class="logo"/>Kuasarr</h1>
            <p><b>Error:</b> Package not found or already solved.</p>
            <p>
                {render_button("Back", "secondary", {"onclick": "location.href='/captcha'"})}
            </p>
            '''),
            content_type="text/html"
        )


def decode_payload():
    """Decode base64 payload from query string."""
    encoded = request.query.get('data')
    try:
        decoded = urlsafe_b64decode(unquote(encoded)).decode()
        return json.loads(decoded)
    except Exception as e:
        return {"error": f"Failed to decode payload: {str(e)}"}


def is_junkies_link(link):
    """Check if link is a Junkies link (sj/dj hostnames)."""
    url = link[0] if isinstance(link, (list, tuple)) else link
    mirror = link[1] if isinstance(link, (list, tuple)) and len(link) > 1 else ""
    sj = shared_state.values["config"]("Hostnames").get("sj") or ""
    dj = shared_state.values["config"]("Hostnames").get("dj") or ""
    return (mirror == "junkies" or 
            (sj and sj in url) or 
            (dj and dj in url))


def is_keeplinks_link(link):
    """Check if link is a KeepLinks link."""
    url = link[0] if isinstance(link, (list, tuple)) else link
    mirror = link[1] if isinstance(link, (list, tuple)) and len(link) > 1 else ""
    return "keeplinks" in url.lower() or "keeplinks" in mirror.lower()


def is_hide_link(link):
    """Check if link is a hide.cx link."""
    url = link[0] if isinstance(link, (list, tuple)) else link
    return "hide.cx" in url.lower()


def is_tolink_link(link):
    """Check if link is a ToLink link."""
    url = link[0] if isinstance(link, (list, tuple)) else link
    mirror = link[1] if isinstance(link, (list, tuple)) and len(link) > 1 else ""
    return "tolink." in url.lower() or "tolink" in mirror.lower()
